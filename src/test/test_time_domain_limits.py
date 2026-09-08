"""The Time Domain window's y limits fitted to the whole record."""

import numpy as np
import pandas as pd
import pytest

from analyses import time_domain
from utils.measurement import Measurement


def measurement():
    distances = np.arange(20000) * 0.0128
    values = 100.0 + np.sin(2 * np.pi * distances / 40.0) * 5.0
    return Measurement(
        channel_df=pd.DataFrame({"BW": values}),
        channels=["BW"],
        units={"BW": "g/m2"},
        distances=distances,
        cd_distances=distances,
        sample_step=0.0128,
    )


def plotted(**attributes):
    controller = time_domain.AnalysisController(measurement(), "MD")
    controller.band_pass_low = 0.0
    controller.band_pass_high = 10.0
    for key, value in attributes.items():
        setattr(controller, key, value)
    controller.plot()
    return controller


def test_fixed_ylim_puts_a_detail_on_the_whole_records_scale(qt_app):
    detail = plotted(analysis_range_high=10.0, fixed_ylim=True)
    whole = plotted(fixed_ylim=True)

    assert detail.figure.axes[0].get_ylim() == pytest.approx(whole.figure.axes[0].get_ylim())
    low, high = detail.figure.axes[0].get_ylim()
    assert low < 95.5 and high > 104.5  # the record's swing, not the first 10 m's


def test_unfixed_detail_fits_its_own_range(qt_app):
    detail = plotted(analysis_range_high=10.0, fixed_ylim=False)

    low, high = detail.figure.axes[0].get_ylim()
    assert high - low < 6.0
