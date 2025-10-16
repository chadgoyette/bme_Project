from __future__ import annotations

import json
import math
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from PySide6.QtCore import QObject, QTimer

from collector.profiles import Profile
from collector.runtime import CollectorRunner, Metadata, RunConfig, build_backend
from dataprep.schemas import RunMetadata
from dataprep.utils import resample_uniform
from live_test.features_rt import FeatureConfig, RealTimeFeatureExtractor

from .ui import DetectorWindow

STORAGE_ALIASES = {
    "refrigerated": "refrigerated",
    "fridge": "refrigerated",
    "cold": "refrigerated",
    "counter": "countertop",
    "countertop": "countertop",
    "ambient": "countertop",
    "frozen": "frozen",
    "freezer": "frozen",
}


class DetectorController(QObject):
    def __init__(self, view: DetectorWindow) -> None:
        super().__init__()
        self.view = view

        self.profile: Optional[Profile] = None
        self.metadata: Optional[RunMetadata] = None
        self.model = None
        self.label_map: Dict[int, str] = {}
        self.class_names: List[str] = []
        self.classes_: List[int] = []

        self.runner: Optional[CollectorRunner] = None
        self.runner_thread: Optional[threading.Thread] = None
        self.status_queue: queue.Queue[Dict[str, object]] = queue.Queue()
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._poll_queue)

        self._start_timestamp_ms: Optional[int] = None
        self._raw_history = pd.DataFrame(
            columns=["timestamp_ms", "gas_resistance_ohms", "temperature_C", "humidity_pct", "pressure_Pa"]
        )
        self._resampled_processed = 0
        self._extractor: Optional[RealTimeFeatureExtractor] = None
        self._feature_config = FeatureConfig(window_sec=600, stride_sec=60, baseline_sec=60, sample_rate_hz=1.0)
        self._log_path: Optional[Path] = None
        self._log_file = None

        self.view.model_selected.connect(self._on_model_selected)
        self.view.metadata_selected.connect(self._on_metadata_selected)
        self.view.profile_changed.connect(self._on_profile_changed)
        self.view.start_requested.connect(self.start)
        self.view.stop_requested.connect(self.stop)

        current_profile = self.view.combo_profile.currentData()
        if isinstance(current_profile, Profile):
            self._on_profile_changed(current_profile)

    def _on_model_selected(self, path: str) -> None:
        model_path = Path(path)
        self.model = joblib.load(model_path)
        estimator = self.model.named_steps["model"]
        self.classes_ = list(estimator.classes_)
        label_map_path = model_path.parent / "label_map.json"
        if label_map_path.exists():
            payload = json.loads(label_map_path.read_text(encoding="utf-8"))
            self.label_map = {int(idx): label for label, idx in payload.items()}
        else:
            self.label_map = {int(idx): str(idx) for idx in self.classes_}
        self.class_names = [self.label_map.get(int(idx), str(idx)) for idx in self.classes_]
        self.view.set_classes(self.class_names)
        self.view.set_status(f"Loaded model with {len(self.class_names)} classes")

    def _on_metadata_selected(self, path: str) -> None:
        meta_path = Path(path)
        with meta_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        self.metadata = RunMetadata(**payload)
        self.view.set_status("Metadata loaded")

    def _on_profile_changed(self, profile: Profile) -> None:
        self.profile = profile
        self.view.set_status(f"Profile set to {profile.name}")

    def start(self) -> None:
        if self.runner_thread and self.runner_thread.is_alive():
            self.view.set_status("Detector already running")
            return
        if self.model is None:
            self.view.set_status("Load a model before starting")
            return
        if self.metadata is None:
            self.view.set_status("Load metadata before starting")
            return
        if self.profile is None:
            self.view.set_status("Select a heater profile before starting")
            return

        try:
            backend = build_backend(self.profile)
        except Exception as exc:
            self.view.set_status(f"Backend error: {exc}")
            return

        meta = self._build_collector_metadata(self.metadata)
        cycles = self.view.cycles_target()
        skip = self.view.skip_cycles()

        run_config = RunConfig(
            profile=self.profile,
            metadata=meta,
            cycles_target=cycles,
            backend=backend,
            profile_hash=self.profile.hash(),
            skip_cycles=skip,
            status_callback=lambda row: self.status_queue.put(row),
        )

        self.runner = CollectorRunner(run_config)
        self.runner_thread = threading.Thread(target=self._run_worker, daemon=True)
        self.runner_thread.start()

        self._start_timestamp_ms = None
        self._raw_history = pd.DataFrame(
            columns=["timestamp_ms", "gas_resistance_ohms", "temperature_C", "humidity_pct", "pressure_Pa"]
        )
        self._resampled_processed = 0
        self._extractor = RealTimeFeatureExtractor(metadata=self.metadata.dict(), config=self._feature_config)

        self._prepare_log(meta.sample_name)

        self.timer.start()
        self.view.reset_plots()
        self.view.toggle_running(True)
        self.view.set_status("Running (warming up)")
        if self.class_names:
            self.view.update_detections({name: 0.0 for name in self.class_names}, None)

    def stop(self) -> None:
        if self.runner:
            self.runner.config.stop()
        if self._log_file:
            self._log_file.flush()
        self.view.set_status("Stopping...")

    def _run_worker(self) -> None:
        try:
            path = self.runner.run() if self.runner else None
            self.status_queue.put({"__complete__": path})
        except Exception as exc:
            self.status_queue.put({"__error__": str(exc)})

    def _poll_queue(self) -> None:
        try:
            while True:
                payload = self.status_queue.get_nowait()
                if "__complete__" in payload:
                    self._handle_complete(payload.get("__complete__"))
                elif "__error__" in payload:
                    self._handle_error(str(payload["__error__"]))
                else:
                    self._handle_row(payload)
        except queue.Empty:
            pass

    def _handle_complete(self, path: Optional[Path]) -> None:
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self.timer.stop()
        self.view.toggle_running(False)
        if path:
            self.view.set_status(f"Run complete (logged to {path})")
        else:
            self.view.set_status("Run complete")
        self.runner = None
        self.runner_thread = None

    def _handle_error(self, message: str) -> None:
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self.timer.stop()
        self.view.toggle_running(False)
        self.view.set_status(f"Error: {message}")
        self.runner = None
        self.runner_thread = None

    def _handle_row(self, row: Dict[str, object]) -> None:
        def as_float(value: object) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            try:
                return float(value)
            except Exception:
                return float("nan")

        def as_int(value: object) -> int:
            if isinstance(value, int):
                return value
            try:
                return int(float(value))
            except Exception:
                return 0

        cycle = as_int(row.get("cycle_index"))
        warmup = bool(row.get("warmup_cycle"))
        step = as_int(row.get("step_index"))
        heater_temp = as_float(row.get("commanded_heater_temp_C"))
        ticks = as_int(row.get("step_duration_ticks"))
        duration_ms = as_float(row.get("step_duration_ms"))
        gas = as_float(row.get("gas_resistance_ohm"))
        temp = as_float(row.get("sensor_temperature_C"))
        hum = as_float(row.get("sensor_humidity_RH"))
        pressure = as_float(row.get("pressure_Pa"))

        cycle_label = f"Cycle: {cycle + 1 if cycle >= 0 else cycle}"
        if warmup:
            cycle_label += " (warmup)"
        step_label = f"Step: {step}"
        heater_text = "Heater: -" if math.isnan(heater_temp) else f"Heater: {heater_temp:.0f} deg C / {ticks} ticks (~{duration_ms:.0f} ms)"
        gas_text = "Gas: -" if math.isnan(gas) else f"Gas: {gas:.2f} ohm"
        temp_text = "Temp: -" if math.isnan(temp) else f"Temp: {temp:.2f} deg C"
        hum_text = "Humidity: -" if math.isnan(hum) else f"Humidity: {hum:.2f} %"
        pressure_text = "Pressure: -" if math.isnan(pressure) else f"Pressure: {pressure:.2f} Pa"

        self.view.set_step_status(
            cycle_label=cycle_label,
            step_label=step_label,
            heater_text=heater_text,
            gas_text=gas_text,
            temp_text=temp_text,
            hum_text=hum_text,
            pressure_text=pressure_text,
        )

        timestamp_ms = self._relative_timestamp(row.get("timestamp_utc"))
        if math.isnan(gas):
            return

        sample = {
            "timestamp_ms": timestamp_ms,
            "gas_resistance_ohms": gas,
            "temperature_C": temp,
            "humidity_pct": hum,
            "pressure_Pa": pressure,
        }
        self.view.append_samples(pd.DataFrame([sample]))

        if warmup:
            return

        self._append_raw_sample(sample)
        self._process_features()

    def _relative_timestamp(self, timestamp_str: Optional[str]) -> int:
        if not timestamp_str:
            if self._raw_history.empty:
                return 0
            last_ts = int(self._raw_history["timestamp_ms"].iloc[-1])
            return last_ts + 1000
        try:
            dt = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
            ms = int(dt.timestamp() * 1000)
        except Exception:
            if self._raw_history.empty:
                return 0
            last_ts = int(self._raw_history["timestamp_ms"].iloc[-1])
            return last_ts + 1000
        if self._start_timestamp_ms is None:
            self._start_timestamp_ms = ms
        return max(0, ms - self._start_timestamp_ms)

    def _append_raw_sample(self, sample: Dict[str, float]) -> None:
        chunk = pd.DataFrame([sample])
        self._raw_history = pd.concat([self._raw_history, chunk], ignore_index=True)

    def _process_features(self) -> None:
        if self._extractor is None or self.model is None or self._raw_history.empty:
            return
        resampled, _ = resample_uniform(
            self._raw_history,
            target_hz=self._feature_config.sample_rate_hz,
            max_gap_sec=3.0,
        )
        if resampled.empty:
            return
        if len(resampled) <= self._resampled_processed:
            return
        new_rows = resampled.iloc[self._resampled_processed :]
        self._resampled_processed = len(resampled)
        chunk = new_rows[["timestamp_ms", "gas_resistance_ohms", "temperature_C", "humidity_pct", "pressure_Pa"]]
        features = self._extractor.ingest(chunk)
        if not features:
            return
        df = pd.DataFrame(features)
        probabilities = self.model.predict_proba(df)
        for idx, row in enumerate(probabilities):
            prob_map = {self.class_names[i]: float(row[i]) for i in range(len(self.class_names))}
            winner_idx = int(np.argmax(row))
            winner = self.class_names[winner_idx]
            self.view.update_detections(prob_map, winner)
            feat_row = features[idx]
            self._write_log_row(feat_row, prob_map, winner)
            if self.view.label_status.text().startswith("Status: Running"):
                continue
            self.view.set_status("Running (collecting)")

    def _build_collector_metadata(self, metadata: RunMetadata) -> Metadata:
        storage_value = metadata.storage_condition.lower()
        storage = STORAGE_ALIASES.get(storage_value, "other")
        return Metadata(
            sample_name=metadata.run_id or metadata.specimen_id,
            specimen_id=metadata.specimen_id,
            storage=storage,
            notes=metadata.notes or "",
        )

    def _prepare_log(self, sample_name: str) -> None:
        log_dir = Path("logs") / "detector"
        log_dir.mkdir(parents=True, exist_ok=True)
        safe_sample = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in sample_name)
        filename = f"inference_{safe_sample}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        self._log_path = log_dir / filename
        header = ["timestamp_ms"] + self.class_names + ["winner", "window_start_ms", "window_end_ms"]
        self._log_file = self._log_path.open("w", encoding="utf-8")
        self._log_file.write(",".join(header) + "\n")

    def _write_log_row(self, features: Dict[str, object], prob_map: Dict[str, float], winner: str) -> None:
        if not self._log_file:
            return
        timestamp = features.get("window_end_ms", 0)
        start_ms = features.get("window_start_ms", 0)
        line = [str(timestamp)]
        for name in self.class_names:
            line.append(f"{prob_map.get(name, 0.0):.6f}")
        line.extend([winner, str(start_ms), str(timestamp)])
        self._log_file.write(",".join(line) + "\n")
        self._log_file.flush()

