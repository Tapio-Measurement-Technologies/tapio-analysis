"""Numerical tests for the floc distribution.

Each test pins the result to a case whose answer can be counted by hand, so a
change in the run detection, the binning or the percentage convention fails
loudly instead of quietly changing what a floc report says.
"""

import numpy as np
import pandas as pd
import pytest

import settings
from analyses import floc_distribution
from utils import floc
from utils.measurement import Measurement

SAMPLE_STEP = 0.0008  # 0.8 mm, the high resolution step of the legacy tool
FS = 1.0 / SAMPLE_STEP


def md_measurement(channels, sample_step=SAMPLE_STEP):
    length = len(next(iter(channels.values())))
    distances = np.arange(length) * sample_step
    return Measurement(
        channel_df=pd.DataFrame(channels),
        channels=list(channels),
        units={name: "g/m2" for name in channels},
        distances=distances,
        cd_distances=distances,
        sample_step=sample_step,
        measurement_label="synthetic",
    )


# --------------------------------------------------------------------------
# Run detection
# --------------------------------------------------------------------------

def test_run_lengths_count_contiguous_stretches_including_the_ends():
    # Runs above 0.5: 2 samples at the start, 3 in the middle, 1 at the end.
    values = np.array([1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0])
    runs = floc.exceedance_run_lengths(values, 0.5)
    assert sorted(runs.tolist()) == [1, 2, 3]


def test_a_negative_limit_looks_below_it():
    values = np.array([0.0, -2.0, -2.0, 0.0, 2.0, 2.0, 2.0])
    below = floc.exceedance_run_lengths(values, -1.0)
    above = floc.exceedance_run_lengths(values, 1.0)
    assert below.tolist() == [2]
    assert above.tolist() == [3]


def test_non_finite_samples_break_a_run_instead_of_joining_it():
    values = np.array([2.0, 2.0, np.nan, 2.0, 2.0])
    runs = floc.exceedance_run_lengths(values, 1.0)
    assert runs.tolist() == [2, 2]


def test_no_exceedance_gives_no_flocs():
    values = np.linspace(-0.5, 0.5, 100)
    assert len(floc.exceedance_run_lengths(values, 1.0)) == 0


# --------------------------------------------------------------------------
# Distribution and statistics
# --------------------------------------------------------------------------

def test_shares_are_the_length_the_flocs_occupy():
    # Two flocs of 3 samples in 1000 samples: 6 samples, 0.6 % of the length,
    # all of it in the bin for 3 sample flocs.
    shares = floc.size_shares(np.array([3, 3]), 1000, bin_count=10)
    assert shares[2] == pytest.approx(0.6)
    assert shares.sum() == pytest.approx(0.6)
    assert np.count_nonzero(shares) == 1


def test_the_last_bin_keeps_the_true_length_of_longer_flocs():
    """A floc longer than the last bin still contributes all of its length.

    Otherwise the cumulative curve would stop short of the share of the
    length that is actually beyond the limit.
    """
    shares = floc.size_shares(np.array([50]), 1000, bin_count=10)
    assert shares[-1] == pytest.approx(5.0)
    assert shares[:-1].sum() == 0.0


def test_statistics_match_a_hand_count():
    # Three flocs, 2 + 4 + 6 = 12 samples out of 1000, over 0.8 m of paper.
    statistics = floc.floc_statistics(
        np.array([2, 4, 6]), 1000, SAMPLE_STEP)
    assert statistics["count"] == 3
    assert statistics["exceeded_percent"] == pytest.approx(1.2)
    assert statistics["mean_size_mm"] == pytest.approx(3.2)   # 4 samples
    assert statistics["flocs_per_m"] == pytest.approx(3 / 0.8)


def test_cumulative_shares_end_at_the_exceeded_percentage():
    runs = np.array([1, 2, 2, 5, 9])
    total = 2000
    shares = floc.size_shares(runs, total, bin_count=30)
    statistics = floc.floc_statistics(runs, total, SAMPLE_STEP)
    assert np.cumsum(shares)[-1] == pytest.approx(
        statistics["exceeded_percent"])


def test_limits_follow_the_entered_positive_limit():
    assert floc.limit_set(1.5) == [
        ("Limit++", 3.0), ("Limit+", 1.5), ("Limit-", -1.5), ("Limit--", -3.0)]
    # A negative entry is read as its magnitude rather than inverting the set.
    assert floc.limit_set(-1.5)[1][1] == 1.5


# --------------------------------------------------------------------------
# The filter
# --------------------------------------------------------------------------

def test_high_pass_removes_slow_variation_and_keeps_the_fast():
    distances = np.arange(20000) * SAMPLE_STEP
    slow = 20.0 * np.sin(2 * np.pi * 1.0 * distances)     # 1 m wavelength
    fast = 2.0 * np.sin(2 * np.pi * 50.0 * distances)     # 2 cm wavelength
    filtered = floc.high_pass(100.0 + slow + fast, 10.0, FS)

    assert np.mean(filtered) == pytest.approx(0.0, abs=0.05)
    # The slow component would dominate the spread if it survived.
    assert np.std(filtered) == pytest.approx(np.std(fast), rel=0.1)


def test_high_pass_without_a_usable_band_only_centres_the_data():
    values = np.linspace(80.0, 120.0, 500)
    filtered = floc.high_pass(values, 0.0, FS)
    assert np.mean(filtered) == pytest.approx(0.0)
    assert np.allclose(filtered, values - np.mean(values))


# --------------------------------------------------------------------------
# End to end through the controller
# --------------------------------------------------------------------------

def square_bumps(length, period, width, height):
    """A signal with one rectangular bump of ``width`` samples every ``period``."""
    values = np.zeros(length)
    positions = np.arange(0, length - width, period)
    for start in positions:
        values[start:start + width] = height
    return values, len(positions)


def test_controller_counts_the_bumps_it_was_given(qt_app):
    """A known number of known width bumps must come back as those flocs."""
    length, period, width, height = 40000, 100, 10, 5.0
    bumps, bump_count = square_bumps(length, period, width, height)
    # Transmission is what the estimate is built from; basis weight only fixes
    # the scale of the straight line fit, so a 1:1 relation keeps the bumps at
    # their own height.
    measurement = md_measurement({
        "Transmission": 100.0 + bumps,
        "BW": 100.0 + bumps,
    })

    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    # The bumps are 8 mm wide, so the filter has to pass them: 10 1/m keeps
    # everything of 10 cm and shorter.
    controller.high_pass_1m = 10.0

    results = controller.calculate()
    shares = {statistics["name"]: (share, statistics)
              for share, _cumulative, statistics in results}

    _share, positive = shares["Limit+"]
    assert positive["count"] == pytest.approx(bump_count, rel=0.02)
    assert positive["mean_size_mm"] == pytest.approx(
        1000 * width * SAMPLE_STEP, rel=0.15)
    assert positive["exceeded_percent"] == pytest.approx(
        100.0 * width / period, rel=0.15)
    # The bumps only go up, so the negative limit must see far less of the
    # length than the positive one. It does not see none: a high pass filter
    # rings at a step edge, and that undershoot is real signal at this cutoff.
    assert (shares["Limit-"][1]["exceeded_percent"]
            < 0.25 * positive["exceeded_percent"])


def test_controller_reports_the_derived_channel_when_transmission_is_present(qt_app):
    measurement = md_measurement({
        "Transmission": np.random.default_rng(3).normal(50.0, 1.0, 5000),
        "BW": np.random.default_rng(4).normal(100.0, 2.0, 5000),
    })
    controller = floc_distribution.AnalysisController(measurement, "MD")
    assert controller.channel == settings.FLOC_DERIVED_BW_LABEL
    assert controller.uses_derived_channel
    assert controller.channel_unit == "g/m2"


def test_controller_falls_back_to_a_measured_channel_without_transmission(qt_app):
    measurement = md_measurement({
        "Caliper": np.random.default_rng(5).normal(200.0, 5.0, 5000),
    })
    controller = floc_distribution.AnalysisController(measurement, "MD")
    assert controller.can_calculate
    assert not controller.uses_derived_channel
    assert controller.channel == "Caliper"
    assert settings.FLOC_DERIVED_BW_LABEL not in controller.available_channels
    assert controller.calculate() is not None
