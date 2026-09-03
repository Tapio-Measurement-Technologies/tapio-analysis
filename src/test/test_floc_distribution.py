"""Numerical tests for the floc distribution.

Each test pins the result to a case whose answer can be counted by hand, so a
change in the run detection, the binning or the percentage convention fails
loudly instead of quietly changing what a floc report says.
"""

import matplotlib.text
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


# --------------------------------------------------------------------------
# Normalisation: the distribution the figure draws
# --------------------------------------------------------------------------

def test_normalized_shares_add_up_to_a_hundred_percent():
    """The plotted distribution is measured against the flocs, not the sheet."""
    runs = np.array([1, 2, 2, 5, 9])
    shares = floc.normalized_size_shares(runs, 2000, bin_count=30)
    assert shares.sum() == pytest.approx(100.0)


def test_normalisation_only_rescales_the_absolute_shares():
    """Nothing is reweighted: the shape is the length weighted one throughout."""
    runs = np.array([1, 2, 2, 5, 9])
    absolute = floc.size_shares(runs, 2000, bin_count=30)
    normalized = floc.normalized_size_shares(runs, 2000, bin_count=30)
    assert normalized == pytest.approx(100.0 * absolute / absolute.sum())
    # Length weighted, not count weighted: two 2 sample flocs occupy 4 samples
    # and one 9 sample floc occupies 9, so the longer one carries more of the
    # distribution despite there being fewer of them.
    assert normalized[8] > normalized[1]


def test_normalisation_of_an_empty_floc_set_is_zeros_not_nans():
    shares = floc.normalized_size_shares(np.zeros(0, dtype=int), 1000,
                                         bin_count=10)
    assert np.all(shares == 0.0)
    assert np.all(np.isfinite(shares))
    assert np.all(np.isfinite(np.cumsum(shares)))


def test_normalisation_leaves_the_absolute_shares_alone():
    """``size_shares`` keeps its old meaning; normalising is a separate step."""
    runs = np.array([3, 3])
    assert floc.size_shares(runs, 1000, bin_count=10).sum() == pytest.approx(0.6)


def test_a_single_floc_length_takes_the_whole_distribution():
    shares = floc.normalized_size_shares(np.array([4, 4, 4]), 500, bin_count=10)
    assert shares[3] == pytest.approx(100.0)
    assert np.count_nonzero(shares) == 1


def test_the_last_bin_keeps_the_true_length_of_longer_flocs():
    """A floc longer than the last bin still contributes all of its length.

    Otherwise the cumulative curve would stop short of the share of the
    length that is actually beyond the limit.
    """
    shares = floc.size_shares(np.array([50]), 1000, bin_count=10)
    assert shares[-1] == pytest.approx(5.0)
    assert shares[:-1].sum() == 0.0


def test_the_last_bin_collects_every_longer_floc_by_its_true_length():
    """Truncating the long flocs to the bin would lose the length they hold.

    10 + 40 + 100 samples all land in the last bin of a 10 bin axis, and the
    bin has to weigh 150 samples rather than 3 x 10.
    """
    shares = floc.size_shares(np.array([10, 40, 100]), 1000, bin_count=10)
    assert shares[-1] == pytest.approx(15.0)
    # Normalising cannot rescue a lost length either, so check both.
    normalized = floc.normalized_size_shares(np.array([10, 40, 100]), 1000,
                                             bin_count=10)
    assert normalized[-1] == pytest.approx(100.0)


def test_a_floc_exactly_at_the_last_bin_is_not_pushed_past_it():
    shares = floc.size_shares(np.array([10]), 1000, bin_count=10)
    assert shares[-1] == pytest.approx(1.0)
    assert shares[:-1].sum() == 0.0


def test_statistics_match_a_hand_count():
    # Three flocs, 2 + 4 + 6 = 12 samples out of 1000, over 0.8 m of paper.
    statistics = floc.floc_statistics(
        np.array([2, 4, 6]), 1000, SAMPLE_STEP)
    assert statistics["count"] == 3
    assert statistics["exceeded_percent"] == pytest.approx(1.2)
    assert statistics["mean_size_mm"] == pytest.approx(3.2)   # 4 samples
    assert statistics["flocs_per_m"] == pytest.approx(3 / 0.8)


def test_cumulative_absolute_shares_end_at_the_exceeded_percentage():
    runs = np.array([1, 2, 2, 5, 9])
    total = 2000
    shares = floc.size_shares(runs, total, bin_count=30)
    statistics = floc.floc_statistics(runs, total, SAMPLE_STEP)
    assert np.cumsum(shares)[-1] == pytest.approx(
        statistics["exceeded_percent"])


# --------------------------------------------------------------------------
# Counting flocs: what the figure draws
# --------------------------------------------------------------------------

def test_each_floc_counts_once_in_the_bin_for_its_length():
    counts = floc.floc_counts_by_length(np.array([1, 1, 1, 2, 2, 4]),
                                        bin_count=4)
    assert counts.tolist() == [3, 2, 0, 1]


def test_frequency_is_the_counts_over_the_analysed_length():
    frequency = floc.floc_frequency_per_m(np.array([1, 1, 1, 2, 2, 4]), 10.0,
                                          bin_count=4)
    assert frequency == pytest.approx([0.3, 0.2, 0.0, 0.1])


def test_the_frequency_bins_add_up_to_the_flocs_per_metre():
    """The height of the distribution and the table's total are one number."""
    runs = np.array([1, 1, 2, 3, 3, 3, 7])
    total_samples = 12500                      # 10 m at a 0.8 mm step
    frequency = floc.floc_frequency_per_m(
        runs, total_samples * SAMPLE_STEP, bin_count=30)
    statistics = floc.floc_statistics(runs, total_samples, SAMPLE_STEP)
    assert frequency.sum() == pytest.approx(statistics["flocs_per_m"])


def test_the_count_shares_are_percentages_of_the_flocs_found():
    shares = floc.normalized_count_shares(np.array([1, 1, 1, 2, 2, 4]),
                                          bin_count=4)
    assert shares == pytest.approx([50.0, 100 / 3, 0.0, 100 / 6])
    assert np.cumsum(shares)[-1] == pytest.approx(100.0)


def test_the_last_count_bin_holds_one_count_per_long_floc():
    """A floc five times the last bin long is one floc, not five bins of length.

    This is where a count parts company with the length weighted shares, which
    would give the same three flocs 4 + 5 + 20 = 29 samples of weight.
    """
    counts = floc.floc_counts_by_length(np.array([4, 5, 20]), bin_count=4)
    assert counts.tolist() == [0, 0, 0, 3]


def test_an_empty_floc_set_counts_to_zero_without_nans():
    empty = np.zeros(0, dtype=int)
    counts = floc.floc_counts_by_length(empty, bin_count=10)
    frequency = floc.floc_frequency_per_m(empty, 100.0, bin_count=10)
    shares = floc.normalized_count_shares(empty, bin_count=10)
    assert counts.tolist() == [0] * 10
    assert np.all(frequency == 0.0)
    assert np.all(shares == 0.0)
    assert np.all(np.isfinite(np.cumsum(shares)))


def test_frequency_without_an_analysed_length_is_zero_not_infinite():
    frequency = floc.floc_frequency_per_m(np.array([1, 2]), 0.0, bin_count=4)
    assert np.all(frequency == 0.0)


def test_counting_flocs_is_not_the_same_as_weighing_their_length():
    """One long floc and many short ones: the two families disagree, correctly."""
    runs = np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 10])
    counts = floc.normalized_count_shares(runs, bin_count=10)
    lengths = floc.normalized_size_shares(runs, 1000, bin_count=10)
    # Ten flocs in eleven are one sample long, but they cover only half the
    # floc covered length, because the eleventh is ten samples long.
    assert counts[0] == pytest.approx(100 * 10 / 11)
    assert lengths[0] == pytest.approx(50.0)


# --------------------------------------------------------------------------
# The floc length axis
# --------------------------------------------------------------------------

def test_a_k_sample_floc_sits_at_its_own_physical_length():
    """Bin k is k sample steps long, not half a step short of it."""
    lengths = floc.bin_lengths_mm(0.0128, bin_count=30)
    assert lengths[0] == pytest.approx(12.8)
    assert lengths[1] == pytest.approx(25.6)
    assert lengths[2] == pytest.approx(38.4)
    assert lengths[-1] == pytest.approx(384.0)
    assert lengths == pytest.approx(
        np.arange(1, 31) * 1000.0 * 0.0128)


def test_the_old_bin_centres_name_gives_the_same_lengths():
    """Kept for the report library, which imports it by the former name."""
    assert floc.bin_centres_mm(SAMPLE_STEP) == pytest.approx(
        floc.bin_lengths_mm(SAMPLE_STEP))


def test_the_bin_axis_is_as_long_as_the_distribution():
    runs = np.array([2, 7])
    shares = floc.size_shares(runs, 1000, bin_count=settings.FLOC_BIN_COUNT)
    assert len(floc.bin_lengths_mm(SAMPLE_STEP)) == len(shares)


# --------------------------------------------------------------------------
# How a limit is written on the figure
# --------------------------------------------------------------------------

def test_a_threshold_reads_as_the_condition_it_is():
    assert floc.threshold_label(2.0, "g/m2") == "> +2 g/m\u00b2"
    assert floc.threshold_label(1.0, "g/m2") == "> +1 g/m\u00b2"
    assert floc.threshold_label(-1.0, "g/m2") == "< -1 g/m\u00b2"
    assert floc.threshold_label(-2.0, "g/m2") == "< -2 g/m\u00b2"


def test_a_threshold_takes_the_unit_of_the_channel_it_was_set_on():
    assert floc.threshold_label(0.5, "um") == "> +0.5 um"
    assert floc.threshold_label(-0.5, "") == "< -0.5"


def test_flocs_of_one_sample_are_not_dropped():
    """The shortest floc the sampling can hold is one sample, and it counts."""
    shares = floc.normalized_size_shares(np.array([1, 1, 1]), 100, bin_count=10)
    assert shares[0] == pytest.approx(100.0)


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
    by_name = {result.statistics["name"]: result for result in results}

    positive = by_name["Limit+"].statistics
    assert positive["count"] == pytest.approx(bump_count, rel=0.02)
    assert positive["mean_size_mm"] == pytest.approx(
        1000 * width * SAMPLE_STEP, rel=0.15)
    assert positive["exceeded_percent"] == pytest.approx(
        100.0 * width / period, rel=0.15)
    # The bumps only go up, so the negative limit must see far less of the
    # length than the positive one. It does not see none: a high pass filter
    # rings at a step edge, and that undershoot is real signal at this cutoff.
    assert (by_name["Limit-"].statistics["exceeded_percent"]
            < 0.25 * positive["exceeded_percent"])


def test_the_length_shares_still_add_up_to_the_exceeded_percentage(qt_app):
    """Counting flocs on the figure must not disturb the length statistic."""
    length, period, width, height = 40000, 100, 10, 5.0
    bumps, _count = square_bumps(length, period, width, height)
    measurement = md_measurement({"Transmission": 100.0 + bumps,
                                  "BW": 100.0 + bumps})
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 10.0

    for result in controller.calculate():
        assert result.length_shares.sum() == pytest.approx(
            result.statistics["exceeded_percent"])
        # And the count family answers the other question over the same runs.
        assert result.counts.sum() == result.statistics["count"]
        assert result.frequency_per_m.sum() == pytest.approx(
            result.statistics["flocs_per_m"])


def test_every_threshold_that_found_a_floc_ends_its_curve_at_a_hundred(qt_app):
    length, period, width, height = 40000, 100, 10, 5.0
    bumps, _count = square_bumps(length, period, width, height)
    measurement = md_measurement({"Transmission": 100.0 + bumps,
                                  "BW": 100.0 + bumps})
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 10.0

    for result in controller.calculate():
        assert np.all(np.isfinite(result.frequency_per_m))
        if result.statistics["count"] > 0:
            assert result.cumulative_count_percent[-1] == pytest.approx(100.0)
        else:
            assert result.cumulative_count_percent[-1] == 0.0


def test_a_limit_no_sample_reaches_draws_nothing_rather_than_failing(qt_app):
    """An empty floc set has no total to divide by, and must not become NaN."""
    measurement = md_measurement({
        "Transmission": np.random.default_rng(11).normal(50.0, 0.1, 5000),
        "BW": np.random.default_rng(12).normal(100.0, 0.1, 5000),
    })
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1000.0
    controller.high_pass_1m = 10.0

    for result in controller.calculate():
        assert result.statistics["count"] == 0
        assert result.statistics["exceeded_percent"] == pytest.approx(0.0)
        assert np.all(result.counts == 0)
        assert np.all(result.frequency_per_m == 0.0)
        assert np.all(result.cumulative_count_percent == 0.0)
        assert np.all(result.length_shares == 0.0)


def test_a_cd_sample_boundary_cannot_join_two_flocs(qt_app):
    """Two profiles that both end and start beyond the limit are two flocs.

    Concatenating the profiles before thresholding would report one floc of
    twice the length, and the CD figure would show flocs the sheet never had.
    """
    # A step edge would ring under the filter, so the limits are applied to the
    # profiles directly: no usable band means high_pass only centres the data.
    # One profile ends beyond the limit and the next one starts beyond it, so
    # joining them would put six samples against six and read one long floc.
    profiles = [np.array([-5.0] * 6 + [5.0] * 6),
                np.array([5.0] * 6 + [-5.0] * 6)]
    joined = [np.concatenate(profiles)]

    separate = floc_distribution_runs(profiles)
    together = floc_distribution_runs(joined)
    assert separate.statistics["count"] == 2
    assert separate.statistics["mean_size_mm"] == pytest.approx(
        1000 * 6 * SAMPLE_STEP)
    # What the CD analysis must not do, shown for contrast.
    assert together.statistics["count"] == 1
    assert together.statistics["mean_size_mm"] == pytest.approx(
        1000 * 12 * SAMPLE_STEP)
    # The length beyond the limit is the same either way; only the split moves.
    assert together.statistics["exceeded_percent"] == pytest.approx(
        separate.statistics["exceeded_percent"])


def floc_distribution_runs(profiles):
    return floc.floc_distribution(profiles, SAMPLE_STEP, 1.0, 0.0,
                                  bin_count=30)


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


# --------------------------------------------------------------------------
# What the figure says
# --------------------------------------------------------------------------

def cd_measurement(profiles, sample_step=SAMPLE_STEP):
    """A CD measurement whose samples are the given profiles."""
    distances = np.arange(len(profiles[0])) * sample_step
    return Measurement(
        channel_df=pd.DataFrame({"Transmission": profiles[0], "BW": profiles[0]}),
        channels=["Transmission", "BW"],
        units={"Transmission": "%", "BW": "g/m2"},
        distances=distances,
        cd_distances=distances,
        sample_step=sample_step,
        measurement_label="synthetic",
        segments={"Transmission": list(profiles), "BW": list(profiles)},
        selected_samples=list(range(len(profiles))),
    )


def test_cd_samples_are_thresholded_one_profile_at_a_time(qt_app):
    """A floc at the end of one sample and one at the start of the next are two.

    The profiles are pooled for the percentages but never concatenated before
    the limits are applied, so the sample boundary cannot manufacture a floc of
    twice the length.
    """
    bump = np.zeros(2000)
    bump[:40] = 6.0          # a floc at the very start of the profile
    bump[-40:] = 6.0         # and one at the very end
    measurement = cd_measurement([100.0 + bump, 100.0 + bump])

    controller = floc_distribution.AnalysisController(measurement, "CD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.cd_distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 0.0     # no filtering, so the bumps stay square

    by_name = {result.statistics["name"]: result
               for result in controller.calculate()}
    positive = by_name["Limit+"].statistics
    # Two profiles, two bumps each: four flocs of 40 samples, never two of 80.
    assert positive["count"] == 4
    assert positive["mean_size_mm"] == pytest.approx(1000 * 40 * SAMPLE_STEP)
    # The percentages are taken over the pooled length of both profiles.
    assert controller.analysed_length_m == pytest.approx(
        2 * 2000 * SAMPLE_STEP)
    assert positive["exceeded_percent"] == pytest.approx(100.0 * 80 / 2000)


def test_the_heading_says_how_much_paper_the_percentages_are_of(qt_app):
    measurement = cd_measurement([np.random.default_rng(seed).normal(
        100.0, 2.0, 2000) for seed in range(3)])
    controller = floc_distribution.AnalysisController(measurement, "CD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.cd_distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 10.0
    controller.updatePlot()

    assert controller.plot_failed is False
    assert "3 samples" in controller.analysed_length_label()
    assert "m analysed" in controller.analysed_length_label()


def test_the_direction_is_not_repeated_when_the_name_already_says_it(qt_app):
    controller = floc_controller(qt_app)
    controller.measurement.measurement_label = "MD reel 4"
    controller.updatePlot()
    heading = controller.figure.get_suptitle()
    assert heading == "MD reel 4 \u2014 Floc length distribution"

    controller.measurement.measurement_label = "reel 4"
    controller.updatePlot()
    assert controller.figure.get_suptitle() == (
        "MD reel 4 \u2014 Floc length distribution")



def floc_controller(qt_app):
    length, period, width, height = 40000, 100, 10, 5.0
    bumps, _count = square_bumps(length, period, width, height)
    measurement = md_measurement({"Transmission": 100.0 + bumps,
                                  "BW": 100.0 + bumps})
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 10.0
    return controller


def long_floc_controller(qt_app):
    """A measurement whose flocs run off the end of the bin axis."""
    length = 40000
    values = np.zeros(length)
    # 400 sample stretches: far longer than the 30 bin axis can name, so they
    # land in the open ended last bin.
    for start in range(0, length - 400, 1000):
        values[start:start + 400] = 5.0
    measurement = md_measurement({"Transmission": 100.0 + values,
                                  "BW": 100.0 + values})
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 0.0     # no filtering, so the stretches stay whole
    return controller


def test_the_axis_stops_where_the_flocs_do(qt_app):
    """Empty bins past the longest floc are not drawn.

    A coarse sample step cannot hold a floc in most of the thirty bins, and
    drawing all of them squeezes the distribution into the first centimetre of
    the panel. The bins are still all calculated.
    """
    controller = floc_controller(qt_app)
    results = controller.calculate()
    occupied = max(int(np.max(np.nonzero(result.counts)[0]))
                   for result in results if np.any(result.counts))

    visible = controller.visible_bin_count(results)
    assert visible == occupied + 2
    assert visible < settings.FLOC_BIN_COUNT
    # Nothing is cut away: every bin beyond the view is empty for every limit.
    for result in results:
        assert result.counts[visible:].sum() == 0

    controller.updatePlot()
    lengths = controller.bin_lengths_mm()
    step_mm = 1000.0 * controller.measurement.sample_step
    assert controller.figure.axes[0].get_xlim()[1] == pytest.approx(
        lengths[visible - 1] + 0.5 * step_mm)


def test_the_last_tick_says_the_last_bin_is_open_ended(qt_app):
    """When the open ended bin is in view, its tick says that it is."""
    controller = long_floc_controller(qt_app)
    results = controller.calculate()
    assert controller.visible_bin_count(results) == settings.FLOC_BIN_COUNT

    controller.updatePlot()
    lengths = controller.bin_lengths_mm()
    formatter = controller.figure.axes[1].xaxis.get_major_formatter()
    assert formatter(lengths[-1], 0) == "\u226524"
    assert formatter(lengths[4], 0) == "4"


def test_a_trimmed_axis_does_not_claim_an_open_ended_bin(qt_app):
    """The ">=" belongs to the last bin, so it goes when that bin is not shown."""
    controller = floc_controller(qt_app)
    controller.updatePlot()
    lengths = controller.bin_lengths_mm()
    formatter = controller.figure.axes[1].xaxis.get_major_formatter()
    assert "\u2265" not in formatter(lengths[-1], 0)


def test_the_ticks_are_floc_lengths_the_sampling_can_produce(qt_app):
    """A 12.8 mm sample step must not label its ticks 13 mm."""
    measurement = md_measurement(
        {"Transmission": np.random.default_rng(9).normal(100.0, 3.0, 20000),
         "BW": np.random.default_rng(9).normal(100.0, 3.0, 20000)},
        sample_step=0.0128)
    controller = floc_distribution.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.limit = 1.0
    controller.high_pass_1m = 10.0
    controller.updatePlot()

    axis = controller.figure.axes[1].xaxis
    formatter = axis.get_major_formatter()
    labels = [formatter(tick, 0) for tick in axis.get_majorticklocs()
              if tick > 0]
    assert "12.8" in labels
    assert "13" not in labels


def test_the_stats_table_reports_thresholds_and_absolute_numbers(qt_app):
    controller = floc_controller(qt_app)
    controller.updatePlot()

    header, (thresholds, values) = controller.getStatsTableData()
    assert header[0] == "Threshold"
    assert "Length beyond [%]" in header[1]
    assert thresholds.splitlines()[0] == "> +2 g/m\u00b2"
    assert thresholds.splitlines()[2] == "< -1 g/m\u00b2"
    # The numbers are the absolute ones, unchanged by the plot normalisation.
    first = controller.floc_stats[0]
    assert values.splitlines()[0].split()[0] == (
        f"{first['exceeded_percent']:.1f}")


def test_the_figure_draws_without_complaint(qt_app):
    """The whole plot path, so a label or a tick change cannot break silently."""
    controller = floc_controller(qt_app)
    controller.updatePlot()
    assert controller.plot_failed is False
    figure = controller.figure

    rendered = " ".join(artist.get_text()
                        for artist in figure.findobj(matplotlib.text.Text))
    assert "Floc length distribution" in rendered
    assert "Floc length [mm]" in rendered
    assert "Floc frequency [1/m]" in rendered
    assert "Cumulative floc count [%]" in rendered
    assert "> +1 g/m\u00b2" in rendered
    assert "% of length" in rendered
    assert "floc = one continuous run beyond the threshold" in rendered
    # The old wording is gone, including the parenthetical about the last bin.
    assert "Floc size" not in rendered
    assert "Limit+" not in rendered
    assert "the last bin holds" not in rendered
    # The plots count flocs now; nothing may still claim to weigh their length.
    assert "floc-covered length" not in rendered
