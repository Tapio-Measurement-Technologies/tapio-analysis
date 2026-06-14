import numpy as np
import pandas as pd

from analyses import correlation_matrix
from utils.measurement import Measurement


def test_cd_correlation_matrix_uses_selected_range_once(qt_app, monkeypatch):
    monkeypatch.setattr(
        correlation_matrix,
        "bandpass_filter",
        lambda data, *_args, **_kwargs: np.asarray(data, dtype=float),
    )
    monkeypatch.setattr(
        correlation_matrix.settings,
        "CORRELATION_MATRIX_SAMPLE_LIMIT",
        5,
    )

    cd_distances = np.arange(10, dtype=float)
    measurement = Measurement(
        channel_df=pd.DataFrame(
            {
                "A": np.arange(10, dtype=float),
                "B": np.arange(20, 30, dtype=float),
            }
        ),
        channels=["A", "B"],
        units={"A": "u", "B": "u"},
        distances=cd_distances,
        cd_distances=cd_distances,
        sample_step=1.0,
        selected_samples=[0, 1],
        segments={
            "A": np.array([
                np.arange(10, dtype=float),
                np.arange(10, 20, dtype=float),
            ]),
            "B": np.array([
                np.arange(20, 30, dtype=float),
                np.arange(30, 40, dtype=float),
            ]),
        },
    )

    controller = correlation_matrix.AnalysisController(measurement, "CD")
    controller.analysis_range_low = 2
    controller.analysis_range_high = 4

    controller.plot()

    assert controller.data_slice["A"].tolist() == [7.0, 8.0, 9.0]
    assert controller.data_slice["B"].tolist() == [27.0, 28.0, 29.0]
