import numpy as np
import pandas as pd

from dataprep.features import compute_window_features
from dataprep.schemas import RunMetadata

from live_test.features_rt import FeatureConfig, ProbabilitySmoother, RealTimeFeatureExtractor


def make_metadata():
    return RunMetadata(
        specimen_id="SPC-LIVE-1",
        meat_type="beef",
        cut="ribeye",
        age_days=2,
        storage_condition="fridge",
        mass_g=100.0,
        jar_id="JAR-02",
        run_id="RUN-LIVE",
        operator="OP",
        protocol_version="1.0",
        heater_profile_id="HP",
        sample_rate_hz=2.0,
        warmup_sec=0,
        exposure_sec=0,
        post_exposure_sec=0,
        room_temp_C=21.0,
        room_rh_pct=40.0,
        notes="",
    )


def test_realtime_feature_matches_dataprep():
    metadata = make_metadata()
    config = FeatureConfig(window_sec=5, stride_sec=5, baseline_sec=0, sample_rate_hz=1.0)
    extractor = RealTimeFeatureExtractor(metadata.dict(), config)
    timestamps = np.arange(0, 5000, 1000)
    chunk = pd.DataFrame(
        {
            "timestamp_ms": timestamps,
            "gas_resistance_ohms": np.linspace(1.0, 2.0, len(timestamps)),
            "temperature_C": np.linspace(20.0, 21.0, len(timestamps)),
            "humidity_pct": np.linspace(40.0, 42.0, len(timestamps)),
            "pressure_Pa": 101325.0,
        }
    )
    features = extractor.ingest(chunk)
    assert len(features) == 1
    dp_window = pd.DataFrame(
        {
            "timestamp_ms": timestamps,
            "gas_resistance_ohms": np.linspace(1.0, 2.0, len(timestamps)),
            "gas_delta": [0.0] * len(timestamps),
            "temperature_C": np.linspace(20.0, 21.0, len(timestamps)),
            "humidity_pct": np.linspace(40.0, 42.0, len(timestamps)),
            "gap_filled": [False] * len(timestamps),
            "gap_unfilled": [False] * len(timestamps),
        }
    )
    dp_features = compute_window_features(dp_window, metadata, sample_rate_hz=1.0)
    assert np.isclose(features[0]["gas_mean"], dp_features["gas_mean"])
    assert np.isclose(features[0]["temperature_mean"], dp_features["temperature_mean"])


def test_probability_smoother_hold_logic():
    smoother = ProbabilitySmoother(alpha=0.5, hold_seconds=2, threshold=0.6, sample_rate_hz=1.0)
    ema, label = smoother.update(np.array([0.8, 0.2]))
    assert label == 0
    ema, label = smoother.update(np.array([0.4, 0.7]))
    # Not enough consecutive calls yet
    assert label == 0
    ema, label = smoother.update(np.array([0.3, 0.8]))
    assert label == 1
