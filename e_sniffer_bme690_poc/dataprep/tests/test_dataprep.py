import pandas as pd
import numpy as np

from dataprep.features import compute_window_features
from dataprep.schemas import RunMetadata
from dataprep.utils import drop_warmup, resample_uniform, sliding_windows


def make_metadata() -> RunMetadata:
    return RunMetadata(
        specimen_id="SPC-1",
        meat_type="beef",
        cut="ribeye",
        age_days=0,
        storage_condition="fridge",
        mass_g=100.0,
        jar_id="JAR-01",
        run_id="RUN-1",
        operator="OP",
        protocol_version="1.0",
        heater_profile_id="HP",
        sample_rate_hz=2.0,
        warmup_sec=60,
        exposure_sec=120,
        post_exposure_sec=0,
        room_temp_C=21.0,
        room_rh_pct=45.0,
        notes="",
    )


def test_drop_warmup_trims_rows():
    df = pd.DataFrame(
        {
            "timestamp_ms": [0, 1000, 2000, 70000],
            "gas_resistance_ohms": [1.0, 1.1, 1.2, 1.3],
            "temperature_C": [20, 20, 20, 20],
            "humidity_pct": [40, 40, 40, 40],
            "pressure_Pa": [101325, 101325, 101325, 101325],
        }
    )
    trimmed = drop_warmup(df, warmup_sec=60)
    assert trimmed.shape[0] == 1
    assert trimmed["timestamp_ms"].iloc[0] == 70000


def test_resample_uniform_interpolates_short_gaps():
    df = pd.DataFrame(
        {
            "timestamp_ms": [0, 1000, 4000],
            "gas_resistance_ohms": [1.0, 2.0, 5.0],
            "temperature_C": [20.0, 20.5, 21.0],
            "humidity_pct": [40.0, 41.0, 42.0],
            "pressure_Pa": [101325, 101330, 101340],
        }
    )
    resampled, gaps = resample_uniform(df, target_hz=1.0, max_gap_sec=3.0)
    # Expect 5 samples (0 through 4 seconds)
    assert resampled.shape[0] == 5
    # Interpolated middle point
    assert np.isclose(resampled.loc[2, "gas_resistance_ohms"], 3.0)
    # No unfilled gaps because gap <= 3 s
    assert gaps.sum() == 0


def test_compute_window_features_basic():
    metadata = make_metadata()
    timestamps = np.arange(0, 6000, 1000)
    window = pd.DataFrame(
        {
            "timestamp_ms": timestamps,
            "gas_resistance_ohms": np.linspace(1.0, 2.0, len(timestamps)),
            "gas_delta": np.linspace(0.0, 1.0, len(timestamps)),
            "temperature_C": np.linspace(20.0, 22.0, len(timestamps)),
            "humidity_pct": np.linspace(40.0, 44.0, len(timestamps)),
            "gap_filled": [False] * len(timestamps),
            "gap_unfilled": [False] * len(timestamps),
        }
    )
    feats = compute_window_features(window, metadata, sample_rate_hz=1.0)
    assert feats["specimen_id"] == metadata.specimen_id
    assert feats["quality_class"] == "clean"
    assert np.isclose(feats["gas_mean"], 1.5)
    assert np.isclose(feats["temperature_range"], 2.0)
    assert feats["freshness_label"] == "fresh"
