from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

VALID_BACKENDS = {"bme68x_i2c", "coines"}
TICK_DURATION_MS = 140

PROFILE_HEADER = {
    "name": "Profile name displayed in the UI.",
    "version": "Schema version integer.",
    "backend": "Target hardware backend identifier.",
    "i2c_addr": "Sensor I2C address string (e.g. 0x76).",
    "steps": "Heater step table.",
    "cycle_target_sec": "Desired duration for full step cycle.",
    "notes": "Optional free-text notes.",
}


@dataclass
class ProfileStep:
    temp_c: int
    ticks: int

    @property
    def duration_ms(self) -> int:
        return self.ticks * TICK_DURATION_MS

    @property
    def ms(self) -> int:
        return self.duration_ms

    @classmethod
    def from_mapping(cls, payload: Dict[str, Any]) -> "ProfileStep":
        if "ticks" in payload:
            ticks = int(payload["ticks"])
        else:
            ms_value = int(payload["ms"])
            ticks = max(1, round(ms_value / TICK_DURATION_MS))
        return cls(
            temp_c=int(payload["temp_c"]),
            ticks=ticks,
        )

    def validate(self) -> None:
        if not 100 <= self.temp_c <= 400:
            raise ValueError(f"Step temperature {self.temp_c} out of range (100-400 C)")
        if not 1 <= self.ticks <= 255:
            raise ValueError(f"Step duration {self.ticks} ticks out of range (1-255 ticks)")


@dataclass
class Profile:
    name: str
    version: int
    backend: str
    i2c_addr: str
    steps: List[ProfileStep]
    cycle_target_sec: float
    notes: str = ""
    path: Path | None = None
    read_only: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Profile name cannot be empty.")
        if self.backend not in VALID_BACKENDS:
            raise ValueError(f"Unsupported backend '{self.backend}'. Expected one of {sorted(VALID_BACKENDS)}.")
        if not self.i2c_addr.startswith("0x"):
            raise ValueError("I2C address must be a hex string like 0x76.")
        if not (1 <= len(self.steps) <= 16):
            raise ValueError("Profiles must contain between 1 and 16 steps.")
        if float(self.cycle_target_sec) < 0:
            raise ValueError("cycle_target_sec must be non-negative.")
        for idx, step in enumerate(self.steps, start=1):
            if not isinstance(step, ProfileStep):
                raise ValueError(f"Step {idx}: Expected ProfileStep, got {type(step)!r}")
            try:
                step.validate()
            except ValueError as exc:
                raise ValueError(f"Step {idx}: {exc}") from exc

    def estimated_cycle_length_sec(self) -> float:
        return sum(step.duration_ms for step in self.steps) / 1000.0


    def to_dict(self) -> Dict[str, Any]:
        cycle_length = self.estimated_cycle_length_sec()
        self.cycle_target_sec = cycle_length
        return {
            "name": self.name,
            "version": self.version,
            "backend": self.backend,
            "i2c_addr": self.i2c_addr,
            "steps": [
                {"temp_c": s.temp_c, "ticks": s.ticks, "ms": s.duration_ms}
                for s in self.steps
            ],
            "cycle_target_sec": cycle_length,
            "notes": self.notes,
        }

    def save(self, path: Path) -> Path:
        payload = self.to_dict()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.path = path
        return path

    @classmethod
    def load(cls, path: Path, read_only: bool = False) -> "Profile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        profile = cls.from_dict(payload, path=path, read_only=read_only)
        profile.validate()
        return profile

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], path: Path | None = None, read_only: bool = False) -> "Profile":
        steps_payload = payload.get("steps", [])
        steps = [ProfileStep.from_mapping(step) for step in steps_payload]
        return cls(
            name=str(payload["name"]),
            version=int(payload.get("version", 1)),
            backend=str(payload.get("backend", "bme68x_i2c")),
            i2c_addr=str(payload.get("i2c_addr", "0x76")),
            steps=steps,
            cycle_target_sec=float(payload.get("cycle_target_sec", 1.0)),
            notes=str(payload.get("notes", "")),
            path=path,
            read_only=read_only,
        )

    def clone(self, name: str | None = None, read_only: bool = False) -> "Profile":
        return Profile(
            name=name or f"{self.name} (Copy)",
            version=self.version,
            backend=self.backend,
            i2c_addr=self.i2c_addr,
            steps=[ProfileStep(temp_c=s.temp_c, ticks=s.ticks) for s in self.steps],
            cycle_target_sec=self.cycle_target_sec,
            notes=self.notes,
            read_only=read_only,
        )

    def hash(self) -> str:
        """Compute SHA1 hash of the persisted contents (file if available)."""
        if self.path and self.path.exists():
            payload = self.path.read_bytes()
        else:
            payload = json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")
        return hashlib.sha1(payload).hexdigest()


DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "Broad Sweep (meat)": {
        "name": "Meat Freshness Sweep v1",
        "version": 1,
        "backend": "bme68x_i2c",
        "i2c_addr": "0x76",
        "steps": [
            {"temp_c": 180, "ticks": 1},
            {"temp_c": 220, "ticks": 1},
            {"temp_c": 260, "ticks": 1},
            {"temp_c": 300, "ticks": 1},
            {"temp_c": 340, "ticks": 1},
        ],
        "cycle_target_sec": 0.7,
        "notes": "Starter broad-spectrum sweep for VOC/spoilage signals",
    },
    "VOC/IAQ": {
        "name": "VOC/IAQ Default",
        "version": 1,
        "backend": "bme68x_i2c",
        "i2c_addr": "0x76",
        "steps": [
            {"temp_c": 150, "ticks": 1},
            {"temp_c": 200, "ticks": 1},
            {"temp_c": 250, "ticks": 1},
            {"temp_c": 300, "ticks": 1},
        ],
        "cycle_target_sec": 0.56,
        "notes": "IAQ-focused sweep",
    },
}


def profile_from_default(name: str) -> Profile:
    payload = DEFAULT_PROFILES[name]
    profile = Profile.from_dict(payload, read_only=True)
    profile.validate()
    return profile


def list_default_profiles() -> List[Profile]:
    return [profile_from_default(name) for name in DEFAULT_PROFILES]
