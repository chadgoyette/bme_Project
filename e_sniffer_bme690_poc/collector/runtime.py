from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from .device import BackendBME68xI2C, BackendBase, BackendCOINES, BackendError, SensorReading
from .logger import CsvLogger
from .profiles import Profile, ProfileStep

LOGGER = logging.getLogger(__name__)


@dataclass
class Metadata:
    sample_name: str
    specimen_id: str
    storage: str
    notes: str = ""
    category: str = ""
    primary_label: str = ""

    @classmethod
    def from_mapping(cls, payload: Dict[str, object]) -> "Metadata":
        sample = str(payload.get("sample_name", "")).strip()
        specimen = str(payload.get("specimen_id", "")).strip()
        storage_raw = payload.get("storage", "")
        storage = str(storage_raw).strip() if storage_raw is not None else ""
        category_raw = payload.get("category")
        primary_raw = payload.get("primary_label")
        category = str(category_raw).strip() if category_raw is not None else ""
        primary_label = str(primary_raw).strip() if primary_raw is not None else ""
        if not sample:
            raise ValueError("sample_name is required")
        if not specimen:
            raise ValueError("specimen_id is required")
        if not storage:
            storage = "unspecified"
        if not category or not primary_label:
            parts = [part.strip() for part in sample.split(">") if part.strip()]
            if not category and parts:
                category = parts[0]
            if not primary_label and len(parts) > 1:
                primary_label = parts[1]
        return cls(
            sample_name=sample,
            specimen_id=specimen,
            storage=storage,
            notes=str(payload.get("notes", "")),
            category=category,
            primary_label=primary_label,
        )


@dataclass
class RunConfig:
    profile: Profile
    metadata: Metadata
    cycles_target: int
    backend: BackendBase
    profile_hash: str
    skip_cycles: int = 0
    stop_event: threading.Event = field(default_factory=threading.Event)
    status_callback: Optional[Callable[[Dict[str, object]], None]] = None
    output_root: Optional[Path] = None

    def stop(self) -> None:
        self.stop_event.set()


class CollectorRunner:
    WARMUP_SECONDS = 10
    STEP_STABILITY_RETRIES = 3

    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.consecutive_failures = 0
        self.logger: Optional[CsvLogger] = None

    def run(self) -> Path:
        profile = self.config.profile
        metadata = self.config.metadata
        profile.validate()
        LOGGER.info(
            "Starting run for sample '%s' with profile '%s' (capture %d cycles, skip first %d)",
            metadata.sample_name,
            profile.name,
            self.config.cycles_target,
            self.config.skip_cycles,
        )
        out_path = self._build_log_path(metadata)
        self.logger = CsvLogger(out_path)
        self.logger.write_header()

        total_cycles_needed = max(0, self.config.skip_cycles) + self.config.cycles_target
        dwell_seconds = max(0.0, float(getattr(profile, "cycle_dwell_sec", 0.0)))
        if dwell_seconds > 0:
            LOGGER.info("Applying %.2f s dwell between cycles", dwell_seconds)
        cycle_index = 0
        captured_cycles = 0
        last_logged_time: Optional[float] = None

        try:
            self._warmup()
            while not self.config.stop_event.is_set() and cycle_index < total_cycles_needed:
                is_warmup_cycle = cycle_index < self.config.skip_cycles
                for step_index, step in enumerate(profile.steps, start=1):
                    reading = self._capture_stable_reading(step)
                    now = time.monotonic()
                    if is_warmup_cycle:
                        elapsed = 0.0
                    else:
                        if last_logged_time is None:
                            elapsed = 0.0
                        else:
                            elapsed = max(0.0, now - last_logged_time)
                        last_logged_time = now
                    row = self._build_row(
                        metadata=metadata,
                        cycle_index=cycle_index,
                        step_index=step_index,
                        step=step,
                        reading=reading,
                        warmup=is_warmup_cycle,
                        elapsed_time_s=elapsed,
                    )
                    if self.config.status_callback:
                        self.config.status_callback(row)
                    if not is_warmup_cycle and self.logger:
                        self.logger.write_row(row)
                        if reading is None:
                            self.consecutive_failures += 1
                            if self.consecutive_failures > 10:
                                raise BackendError("Too many consecutive sensor read failures.")
                        else:
                            self.consecutive_failures = 0
                cycle_index += 1
                if not is_warmup_cycle:
                    captured_cycles += 1
                if (
                    dwell_seconds > 0
                    and not self.config.stop_event.is_set()
                    and cycle_index < total_cycles_needed
                ):
                    slept = 0.0
                    while slept < dwell_seconds and not self.config.stop_event.is_set():
                        chunk = min(0.5, dwell_seconds - slept)
                        try:
                            self.config.backend.sleep(chunk)
                        except AttributeError:
                            time.sleep(chunk)
                        slept += chunk
                    if self.config.status_callback:
                        self.config.status_callback({"__dwell__": slept})
        finally:
            self.config.backend.close()
            if self.logger:
                self.logger.close()
        LOGGER.info(
            "Run finished. Captured %d cycles (warmup skipped %d). CSV stored at %s",
            captured_cycles,
            self.config.skip_cycles,
            out_path,
        )
        return out_path

    def _capture_stable_reading(self, step: ProfileStep) -> Optional[SensorReading]:
        """Request readings until the backend reports heater stability or retries are exhausted."""
        attempts = 0
        last_reading: Optional[SensorReading] = None
        while attempts < self.STEP_STABILITY_RETRIES and not self.config.stop_event.is_set():
            try:
                candidate = self.config.backend.apply_and_read_step(step.temp_c, step.duration_ms)
            except Exception as exc:
                LOGGER.debug("Sensor read failed during stability check: %s", exc)
                candidate = None
            last_reading = candidate
            if candidate and candidate.heat_stable:
                return candidate
            attempts += 1
        if last_reading and not last_reading.heat_stable:
            LOGGER.debug("Heater step at %s C timed out waiting for heat stability", step.temp_c)
        return None

    def _warmup(self) -> None:
        LOGGER.info("Warming up sensor for %s seconds", self.WARMUP_SECONDS)
        profile = self.config.profile
        end_time = time.time() + self.WARMUP_SECONDS
        while time.time() < end_time and not self.config.stop_event.is_set():
            for step in profile.steps:
                self.config.backend.apply_and_read_step(step.temp_c, step.duration_ms)
                if time.time() >= end_time:
                    break

    def _build_log_path(self, metadata: Metadata) -> Path:
        base_root = self.config.output_root if self.config.output_root else Path("logs")
        timestamp = datetime.now(timezone.utc).strftime("%H%M%S")
        date_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def _sanitize(value: str) -> str:
            return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())

        root = Path(base_root)
        if metadata.category:
            root = root / _sanitize(metadata.category)
        if metadata.primary_label:
            root = root / _sanitize(metadata.primary_label)
        root = root / date_dir
        root.mkdir(parents=True, exist_ok=True)

        safe_sample = _sanitize(metadata.sample_name)
        return root / f"bme690_{safe_sample}_{timestamp}.csv"

    def _build_row(
        self,
        metadata: Metadata,
        cycle_index: int,
        step_index: int,
        step: ProfileStep,
        reading,
        warmup: bool,
        elapsed_time_s: float,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "timestamp_utc": CsvLogger.timestamp_string(),
            "elapsed_time_s": round(float(elapsed_time_s), 3),
            "cycle_index": cycle_index,
            "step_index": step_index,
            "commanded_heater_temp_C": step.temp_c,
            "step_duration_ticks": step.ticks,
            "step_duration_ms": step.duration_ms,
            "backend": self.config.profile.backend,
            "i2c_addr": self.config.profile.i2c_addr,
            "sample_name": metadata.sample_name,
            "specimen_id": metadata.specimen_id,
            "storage": metadata.storage,
            "notes": metadata.notes,
            "profile_name": self.config.profile.name,
            "profile_hash": self.config.profile_hash,
            "warmup_cycle": warmup,
        }
        if reading is None:
            payload.update(
                {
                    "gas_resistance_ohm": math.nan,
                    "sensor_temperature_C": math.nan,
                    "sensor_humidity_RH": math.nan,
                    "pressure_Pa": math.nan,
                    "heater_heat_stable": False,
                    "sensor_status_raw": math.nan,
                }
            )
        else:
            payload.update(reading.as_dict())
        return payload


def build_backend(profile: Profile) -> BackendBase:
    try:
        addr = int(profile.i2c_addr, 16)
    except ValueError:
        raise ValueError(f"Invalid I2C address '{profile.i2c_addr}'") from None
    if profile.backend == "bme68x_i2c":
        return BackendBME68xI2C(address=addr)
    if profile.backend == "coines":
        return BackendCOINES(address=addr)
    raise ValueError(f"Unsupported backend '{profile.backend}'")


