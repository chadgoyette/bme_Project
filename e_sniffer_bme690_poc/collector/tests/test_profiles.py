from pathlib import Path

import json
import math

from collector.profiles import Profile, ProfileStep, profile_from_default
from collector.logger import CsvLogger, CSV_HEADER


def test_profile_validation_bounds(tmp_path: Path) -> None:
    profile = Profile(
        name="Test Profile",
        version=1,
        backend="bme68x_i2c",
        i2c_addr="0x76",
        steps=[ProfileStep(temp_c=200, ticks=1)],
        cycle_target_sec=1.0,
    )
    profile.validate()  # should not raise

    profile.steps[0].temp_c = 500
    try:
        profile.validate()
    except ValueError as exc:
        assert "Step 1" in str(exc)
    else:
        raise AssertionError("Expected validation error for temp")


def test_default_profiles_are_valid() -> None:
    default = profile_from_default("Broad Sweep (meat)")
    assert default.read_only
    default.validate()


def test_csv_logger_writes_header(tmp_path: Path) -> None:
    out = tmp_path / "test.csv"
    logger = CsvLogger(out)
    logger.write_header()
    logger.write_row({key: key for key in CSV_HEADER})
    logger.close()
    contents = out.read_text(encoding="utf-8").strip().splitlines()
    assert contents[0] == ",".join(CSV_HEADER)
    assert contents[1].startswith("timestamp_utc")
