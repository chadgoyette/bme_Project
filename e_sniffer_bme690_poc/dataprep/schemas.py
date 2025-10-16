from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError


class RunMetadata(BaseModel):
    specimen_id: str
    meat_type: str
    cut: str
    age_days: int = Field(..., ge=0)
    storage_condition: str
    mass_g: float
    jar_id: str
    run_id: str
    operator: str
    protocol_version: str
    heater_profile_id: str
    sample_rate_hz: float
    warmup_sec: int = 0
    exposure_sec: int = 0
    post_exposure_sec: int = 0
    room_temp_C: float
    room_rh_pct: float
    notes: str = ""
    created_utc: Optional[datetime] = None

    class Config:
        extra = "ignore"

    def label(self) -> str:
        return "fresh" if self.age_days <= 1 else "aged"

    @classmethod
    def from_path(cls, path: Path) -> "RunMetadata":
        data = path.read_text(encoding="utf-8")
        import json

        payload: Dict[str, Any] = json.loads(data)
        try:
            return cls(**payload)
        except ValidationError as exc:  # pragma: no cover - validated in tests
            raise ValueError(f"Invalid metadata at {path}: {exc}") from exc
