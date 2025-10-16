from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from dataprep.schemas import RunMetadata

from .features_rt import FeatureConfig, ProbabilitySmoother, RealTimeFeatureExtractor
from .streaming import ReplayCSVSource, SubprocessSource, TailCSVSource
from .ui import LiveTestWindow

LOGGER = logging.getLogger("live_test")


class LiveController(QObject):
    def __init__(self, view: LiveTestWindow) -> None:
        super().__init__()
        self.view = view
        self.model = None
        self.label_map: Dict[int, str] = {}
        self.csv_path: Optional[Path] = None
        self.metadata: Optional[RunMetadata] = None
        self.mode: str = "Replay CSV"
        self.source = None
        self.extractor: Optional[RealTimeFeatureExtractor] = None
        self.smoother: Optional[ProbabilitySmoother] = None
        self.classes_: List[int] = []
        self.class_names: List[str] = []
        self.log_path: Optional[Path] = None
        self._log_file = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self.view.csv_selected.connect(self._on_csv_selected)
        self.view.metadata_selected.connect(self._on_metadata_selected)
        self.view.model_selected.connect(self._on_model_selected)
        self.view.mode_changed.connect(self._on_mode_changed)
        self.view.start_requested.connect(self.start)
        self.view.stop_requested.connect(self.stop)

    def _on_csv_selected(self, path: str) -> None:
        self.csv_path = Path(path)
        self.view.set_status(f"CSV selected: {self.csv_path.name}")

    def _on_metadata_selected(self, path: str) -> None:
        meta_path = Path(path)
        with meta_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        self.metadata = RunMetadata(**payload)
        self.view.set_status("Metadata loaded")

    def _on_model_selected(self, path: str) -> None:
        model_path = Path(path)
        self.model = joblib.load(model_path)
        estimator = self.model.named_steps["model"]
        self.classes_ = list(estimator.classes_)
        # Attempt to load label map alongside model
        label_map_path = model_path.parent / "label_map.json"
        if label_map_path.exists():
            label_map = json.loads(label_map_path.read_text(encoding="utf-8"))
            self.label_map = {int(v): k for k, v in label_map.items()}
        else:
            self.label_map = {int(idx): str(idx) for idx in self.classes_}
        self.class_names = [self.label_map.get(int(idx), str(idx)) for idx in self.classes_]
        self.view.set_status(f"Model loaded ({len(self.class_names)} classes)")
        self.view.set_classes(self.class_names)

    def _on_mode_changed(self, mode: str) -> None:
        self.mode = mode
        self.view.set_status(f"Mode set to {mode}")

    def start(self) -> None:
        if not self.csv_path or not self.csv_path.exists():
            self.view.set_status("CSV not selected")
            return
        if self.metadata is None:
            self.view.set_status("Metadata not loaded")
            return
        if self.model is None:
            self.view.set_status("Model not loaded")
            return

        config = FeatureConfig(window_sec=600, stride_sec=60, baseline_sec=60, sample_rate_hz=1.0)
        self.extractor = RealTimeFeatureExtractor(self.metadata.dict(), config)

        if self.mode == "Replay CSV":
            self.source = ReplayCSVSource(self.csv_path)
        elif self.mode == "Tail CSV":
            self.source = TailCSVSource(self.csv_path)
        else:
            self.source = SubprocessSource(["track_b_logger_stub"])

        alpha = self.view.alpha_spin.value()
        threshold = self.view.threshold_spin.value()
        hold_sec = self.view.hold_spin.value()
        if self.view.ema_checkbox.isChecked():
            self.smoother = ProbabilitySmoother(alpha=alpha, hold_seconds=hold_sec, threshold=threshold, sample_rate_hz=config.sample_rate_hz)
        else:
            self.smoother = None

        self.log_path = self.csv_path.parent / "inference_log.csv"
        self._log_file = self.log_path.open("w", encoding="utf-8")
        header = ["timestamp_ms"] + self.class_names + ["winner", "window_start_ms", "window_end_ms"]
        self._log_file.write(",".join(header) + "\n")

        self.view.reset_run()
        self.view.update_detections({name: 0.0 for name in self.class_names}, None)

        interval_ms = max(200, int(1000 / config.sample_rate_hz))
        self.timer.start(interval_ms)
        self.view.toggle_running(True)
        self.view.set_status("Streaming started")

    def stop(self) -> None:
        self.timer.stop()
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self.view.toggle_running(False)
        self.view.set_status("Streaming stopped")
        if self.class_names:
            self.view.update_detections({name: 0.0 for name in self.class_names}, None)

    def _tick(self) -> None:
        if self.source is None or self.extractor is None or self.model is None:
            return
        chunk = self.source.next_chunk()
        if chunk.empty:
            return
        self.view.append_samples(chunk)
        feature_rows = self.extractor.ingest(chunk)
        if not feature_rows:
            return
        df = pd.DataFrame(feature_rows)
        proba = self.model.predict_proba(df)
        for idx, row in enumerate(proba):
            ema_probs = row
            winner_idx = int(np.argmax(row))
            if self.smoother is not None:
                ema_probs, smoothed_label = self.smoother.update(row)
                if smoothed_label is not None:
                    winner_idx = smoothed_label
            prob_map = {self.class_names[i]: float(ema_probs[i]) for i in range(len(self.class_names))}
            winner_name = self.class_names[winner_idx]
            winner_confidence = prob_map.get(winner_name, 0.0)
            self.view.update_detections(prob_map, winner_name, winner_confidence)
            feat = feature_rows[idx]
            timestamp = feat["window_end_ms"]
            log_row = [str(timestamp)] + [f"{prob_map[name]:.6f}" for name in self.class_names] + [
                winner_name,
                str(feat["window_start_ms"]),
                str(feat["window_end_ms"]),
            ]
            if self._log_file is not None:
                self._log_file.write(",".join(log_row) + "\n")
                self._log_file.flush()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    window = LiveTestWindow()
    LiveController(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
