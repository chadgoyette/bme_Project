from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable


CSV_HEADER = [
    "timestamp_utc",
    "cycle_index",
    "step_index",
    "commanded_heater_temp_C",
    "step_duration_ticks",
    "step_duration_ms",
    "heater_heat_stable",
    "sensor_status_raw",
    "gas_resistance_ohm",
    "sensor_temperature_C",
    "sensor_humidity_RH",
    "pressure_Pa",
    "backend",
    "i2c_addr",
    "sample_name",
    "specimen_id",
    "storage",
    "notes",
    "profile_name",
    "profile_hash",
]


class CsvLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fp, fieldnames=CSV_HEADER, extrasaction="ignore")

    def write_header(self) -> None:
        self._writer.writeheader()

    def write_row(self, payload: Dict[str, object]) -> None:
        self._writer.writerow(payload)
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()

    @staticmethod
    def timestamp_string() -> str:
        return datetime.now(timezone.utc).isoformat()
