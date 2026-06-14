import importlib.util
import os

import numpy as np
import pandas as pd


def load_parquet_loader_module():
    loader_path = os.path.join(
        os.path.dirname(__file__), "..", "loaders", "tapio-parquet-loader.py"
    )
    spec = importlib.util.spec_from_file_location("tapio_parquet_loader", loader_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parquet_loader_reads_distance_data_and_applies_calibration(
    tmp_path, monkeypatch
):
    loader = load_parquet_loader_module()
    monkeypatch.setattr(loader.settings, "PQ_LOADER_GENERATE_DISTANCES", False)
    monkeypatch.setattr(loader.settings, "CALCULATED_CHANNELS", [])
    monkeypatch.setattr(loader.settings, "IGNORE_CHANNELS", [])

    parquet_path = tmp_path / "sample-data.parquet"
    calibration_path = tmp_path / "sample-calibration.json"
    frame = pd.DataFrame(
        {
            "Distance": np.array([10.000, 10.001, 10.002, 10.003]),
            "Moisture": np.array([1.0, 2.0, 3.0, 4.0]),
        }
    )
    frame.to_parquet(parquet_path, engine="pyarrow")
    calibration_path.write_text(
        '{"Moisture": {"type": "linregr", "unit": "%", "points": [[1, 10], [4, 40]]}}',
        encoding="utf-8",
    )

    measurement = loader.load_data([str(parquet_path), str(calibration_path)])

    assert measurement is not None
    assert measurement.measurement_label == "sample-data"
    assert measurement.data_file_path == "sample-data.parquet"
    assert measurement.calibration_file_path == "sample-calibration.json"
    assert measurement.units["Moisture"] == "%"
    assert np.allclose(measurement.distances, [0.0, 0.001, 0.002, 0.003])
    assert np.allclose(measurement.channel_df["Moisture"], [10.0, 20.0, 30.0, 40.0])


def test_parquet_loader_rejects_file_without_distance_column(tmp_path, monkeypatch):
    loader = load_parquet_loader_module()
    monkeypatch.setattr(loader.settings, "PQ_LOADER_GENERATE_DISTANCES", False)

    parquet_path = tmp_path / "missing-distance.parquet"
    pd.DataFrame({"Moisture": [1.0, 2.0, 3.0]}).to_parquet(
        parquet_path, engine="pyarrow"
    )

    assert loader.load_data([str(parquet_path)]) is None


def test_parquet_loader_reads_without_calibration_file(tmp_path, monkeypatch):
    loader = load_parquet_loader_module()
    monkeypatch.setattr(loader.settings, "PQ_LOADER_GENERATE_DISTANCES", False)
    monkeypatch.setattr(loader.settings, "CALCULATED_CHANNELS", [])
    monkeypatch.setattr(loader.settings, "IGNORE_CHANNELS", [])

    parquet_path = tmp_path / "sample-data.parquet"
    pd.DataFrame(
        {
            "Distance": np.array([0.000, 0.001, 0.002, 0.003]),
            "BW": np.array([1.0, 2.0, 3.0, 4.0]),
        }
    ).to_parquet(parquet_path, engine="pyarrow")

    measurement = loader.load_data([str(parquet_path)])

    assert measurement is not None
    assert measurement.units["BW"] == "V"
    assert list(measurement.channels) == ["BW"]


def test_parquet_loader_preserves_uncalibrated_channels(tmp_path, monkeypatch):
    loader = load_parquet_loader_module()
    monkeypatch.setattr(loader.settings, "PQ_LOADER_GENERATE_DISTANCES", False)
    monkeypatch.setattr(loader.settings, "CALCULATED_CHANNELS", [])
    monkeypatch.setattr(loader.settings, "IGNORE_CHANNELS", [])

    parquet_path = tmp_path / "sample-data.parquet"
    calibration_path = tmp_path / "sample-calibration.json"
    pd.DataFrame(
        {
            "Distance": np.array([0.000, 0.001, 0.002, 0.003]),
            "Moisture": np.array([1.0, 2.0, 3.0, 4.0]),
            "RawOnly": np.array([10.0, 20.0, 30.0, 40.0]),
        }
    ).to_parquet(parquet_path, engine="pyarrow")
    calibration_path.write_text(
        '{"Moisture": {"type": "linregr", "unit": "%", "points": [[1, 10], [4, 40]]}}',
        encoding="utf-8",
    )

    measurement = loader.load_data([str(parquet_path), str(calibration_path)])

    assert measurement is not None
    assert list(measurement.channels) == ["Moisture", "RawOnly"]
    assert measurement.units["Moisture"] == "%"
    assert measurement.units["RawOnly"] == "V"
    assert np.allclose(measurement.channel_df["Moisture"], [10.0, 20.0, 30.0])
    assert np.allclose(measurement.channel_df["RawOnly"], [10.0, 20.0, 30.0])
