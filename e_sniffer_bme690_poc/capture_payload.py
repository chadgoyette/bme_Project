from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from collector.runtime import CollectorRunner, Metadata, RunConfig, build_backend
from collector.profiles import Profile

SDK_PATH = os.getenv("COINES_SDK_PATH")
print("COINES_SDK_PATH:", SDK_PATH)

profile = Profile.from_dict(
    {
        "name": "COINES Debug",
        "version": 1,
        "backend": "coines",
        "i2c_addr": "0x76",
        "steps": [
            {"temp_c": 180, "ms": 150},
            {"temp_c": 220, "ms": 150},
        ],
        "cycle_target_sec": 1.0,
        "notes": "debug capture",
    }
)

profile.validate()

backend = build_backend(profile)

metadata = Metadata(sample_name="debug", specimen_id="S1", storage="other")
config = RunConfig(
    profile=profile,
    metadata=metadata,
    duration_sec=5,
    backend=backend,
    profile_hash=profile.hash(),
)


def capture(row: dict) -> None:
    print("CAPTURE:", row)
    Path("payload_log.txt").write_text(repr(row), encoding="utf-8")


config.status_callback = capture
runner = CollectorRunner(config)

try:
    runner.run()
finally:
    backend.close()
