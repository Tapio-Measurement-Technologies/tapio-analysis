import numpy as np
import pandas as pd

from analyses import (cepstrum, channel_correlation, coherence, formation,
                      spectrogram, spectrum, vca)
from utils.measurement import Measurement


def make_cd_measurement(selected_samples=None):
    distances = np.arange(32, dtype=float)
    return Measurement(
        channel_df=pd.DataFrame(
            {
                "A": np.sin(distances),
                "Basis Weight": np.linspace(50, 55, len(distances)),
                "Transmission": np.linspace(10, 11, len(distances)),
            }
        ),
        channels=["A", "Basis Weight", "Transmission"],
        units={"A": "u", "Basis Weight": "g/m2", "Transmission": "%"},
        distances=distances,
        cd_distances=distances,
        sample_step=1.0,
        selected_samples=selected_samples if selected_samples is not None else [0, 1],
        segments={
            "A": np.array([
                np.sin(distances),
                np.cos(distances),
            ]),
            "Basis Weight": np.array([
                np.linspace(50, 55, len(distances)),
                np.linspace(51, 56, len(distances)),
            ]),
            "Transmission": np.array([
                np.linspace(10, 11, len(distances)),
                np.linspace(10.2, 11.2, len(distances)),
            ]),
        },
    )


def test_cd_spectral_plots_handle_no_selected_samples(qt_app):
    measurement = make_cd_measurement(selected_samples=[])

    for module in (spectrum, coherence, spectrogram):
        controller = module.AnalysisController(measurement, "CD")
        controller.selected_samples = []

        controller.plot()

        assert len(controller.frequencies) == 0


def test_formation_accepts_basis_weight_alias(qt_app):
    measurement = make_cd_measurement()

    controller = formation.AnalysisController(measurement, "MD")

    assert controller.can_calculate
    assert controller.bw_channel == "Basis Weight"


def test_channel_correlation_can_open_with_one_channel(qt_app):
    distances = np.arange(4, dtype=float)
    measurement = Measurement(
        channel_df=pd.DataFrame({"Only": distances}),
        channels=["Only"],
        units={"Only": "u"},
        distances=distances,
        cd_distances=distances,
        sample_step=1.0,
    )

    controller = channel_correlation.AnalysisController(measurement, "MD")

    assert controller.channel == "Only"
    assert controller.channel2 == "Only"


def test_cepstrum_handles_data_shorter_than_the_window(qt_app):
    """A 32-sample record against a 20000-sample window must not raise."""
    measurement = make_cd_measurement()

    controller = cepstrum.AnalysisController(measurement, "MD")
    controller.plot()

    assert len(controller.quefrencies) == len(controller.cepstrum_amplitudes)


def test_cepstrum_handles_an_all_nan_channel(qt_app):
    distances = np.arange(64, dtype=float)
    measurement = Measurement(
        channel_df=pd.DataFrame({"Dead": np.full(len(distances), np.nan)}),
        channels=["Dead"],
        units={"Dead": "u"},
        distances=distances,
        cd_distances=distances,
        sample_step=1.0,
    )

    controller = cepstrum.AnalysisController(measurement, "MD")
    controller.plot()

    assert len(controller.quefrencies) == 0


def test_vca_variance_components_do_not_return_negative_residual(qt_app):
    measurement = make_cd_measurement()
    controller = vca.AnalysisController(measurement, "CD")

    variances = controller.calculate_variances(
        np.array([
            [1.0, 1.0],
            [1.0, 1.0],
        ])
    )

    assert all(value >= 0 for value in variances)
