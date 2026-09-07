"""The CD profile waterfall's spacing between strips."""

import numpy as np
import pandas as pd
import pytest

import settings
from analyses import cd_profile_waterfall
from utils.measurement import Measurement


def strips_measurement(level, sigma, strips=6, length=400, seed=2):
    rng = np.random.default_rng(seed)
    distances = np.arange(length) * 0.01
    segments = np.array([level + rng.normal(0.0, sigma, length) for _ in range(strips)])
    return Measurement(
        channel_df=pd.DataFrame({"X": segments[0]}),
        channels=["X"],
        units={"X": "u"},
        distances=distances,
        cd_distances=distances,
        sample_step=0.01,
        selected_samples=list(range(strips)),
        segments={"X": segments},
    )


def plotted(measurement, **attributes):
    controller = cd_profile_waterfall.AnalysisController(measurement, "CD")
    controller.band_pass_low = 0.0
    controller.band_pass_high = 40.0
    for key, value in attributes.items():
        setattr(controller, key, value)
    controller.plot()
    return controller


def strip_baselines(controller):
    """Where each strip's mean line was drawn: the spacing is their step."""
    return sorted(float(line.get_ydata()[0]) for line in controller.figure.axes[0].lines
                  if line.get_color() == "gray")


def test_automatic_spacing_follows_the_variation_not_the_level(qt_app):
    """Basis weight varies little beside its level, gloss a lot: a percentage
    of the mean spaces one too far and the other on top of each other."""
    high_level = plotted(strips_measurement(level=80.0, sigma=0.5), waterfall_offset=0)
    low_level = plotted(strips_measurement(level=4.0, sigma=0.5), waterfall_offset=0)

    spacing_high = np.diff(strip_baselines(high_level))
    spacing_low = np.diff(strip_baselines(low_level))
    expected = settings.CD_PROFILE_WATERFALL_AUTO_SPACING_SIGMAS * 0.5
    assert spacing_high == pytest.approx(expected, rel=0.15)
    assert spacing_low == pytest.approx(expected, rel=0.15)


def test_percentage_offset_still_scales_with_the_mean(qt_app):
    controller = plotted(strips_measurement(level=80.0, sigma=0.5), waterfall_offset=10)

    assert np.diff(strip_baselines(controller)) == pytest.approx(8.0, rel=0.02)


def test_default_offset_is_automatic(qt_app):
    controller = cd_profile_waterfall.AnalysisController(
        strips_measurement(level=80.0, sigma=0.5), "CD")

    assert controller.waterfall_offset == settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT == 0
