import numpy as np
import pandas as pd

from dataprep.build import FEATURE_COLUMNS, _stack_signals, build_cycle_samples, extract_label_fields


def test_extract_label_fields_parses_sample_name():
    fields = extract_label_fields("Coffee > Dunkin > Hazelnut > Yes > No")
    assert fields["category"] == "Coffee"
    assert fields["primary_label"] == "Dunkin"
    assert fields["target_label"] == "No"
    assert fields["label_path"] == "Coffee / Dunkin / Hazelnut / Yes / No"


def test_extract_label_fields_falls_back_to_raw_string():
    fields = extract_label_fields("LooseLabel")
    assert fields["category"] == "LooseLabel"
    assert fields["primary_label"] == "LooseLabel"
    assert fields["target_label"] == "LooseLabel"
    assert fields["label_path"] == "LooseLabel"


def _make_cycle_dataframe(steps: int = 4) -> pd.DataFrame:
    data = {
        "cycle_index": np.repeat([3, 4], steps),
        "step_index": list(range(1, steps + 1)) * 2,
        "commanded_heater_temp_C": np.tile(np.linspace(200, 320, steps), 2),
        "step_duration_ticks": 32,
        "step_duration_ms": 4480,
        "heater_heat_stable": True,
        "sensor_status_raw": 176,
        "gas_resistance_ohm": np.linspace(10, 100, steps * 2),
        "sensor_temperature_C": 25.0,
        "sensor_humidity_RH": 40.0,
        "pressure_Pa": 101000.0,
        "backend": "coines",
        "i2c_addr": "0x76",
        "sample_name": "Category > Label",
        "specimen_id": "SPEC-1",
        "storage": "fridge",
        "notes": "",
        "profile_name": "Profile-A",
        "profile_hash": "abc123",
    }
    return pd.DataFrame(data)


def test_build_cycle_samples_infers_steps_and_returns_sequences(tmp_path):
    df = _make_cycle_dataframe(steps=5)
    signals, metadata, inferred = build_cycle_samples(df, tmp_path / "file.csv", expected_steps=None, drop_unstable=True)
    assert inferred == 5
    assert len(signals) == 2
    assert all(signal.shape == (5, len(FEATURE_COLUMNS)) for signal in signals)
    assert metadata[0]["target_label"] == "Label"
    assert metadata[0]["specimen_id"] == "SPEC-1"


def test_build_cycle_samples_skips_incomplete_cycles(tmp_path):
    df = _make_cycle_dataframe(steps=4)
    # Introduce NaN in one cycle
    df.loc[df["cycle_index"] == 4, "gas_resistance_ohm"] = np.nan
    signals, metadata, inferred = build_cycle_samples(df, tmp_path / "file.csv", expected_steps=None, drop_unstable=False)
    assert inferred == 4
    assert len(signals) == 1  # one cycle removed
    assert len(metadata) == 1


def test_stack_signals_handles_empty():
    stacked = _stack_signals([], expected_steps=0)
    assert stacked.shape == (0, 0, len(FEATURE_COLUMNS))
