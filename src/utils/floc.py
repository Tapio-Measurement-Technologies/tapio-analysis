"""The floc distribution calculation: filtering, run detection, binning.

Kept apart from the analysis window so that the numbers behind a floc figure
can be computed - and tested - without a GUI, and so that anything else that
needs them (a report, a comparison script) uses this code rather than a copy
of it.

A floc, here, is one contiguous run of samples beyond a limit in the high pass
filtered signal, and what is measured of it is its length along the sample.

Two families of number live here and neither answers for the other.

**How much paper is floc** is length weighted: ``size_shares`` measures the
flocs against the whole analysed length and its sum is ``exceeded_percent``,
and ``normalized_size_shares`` measures them against each other. A long floc
weighs more than a short one in both.

**How many flocs there are** is a count: ``floc_counts_by_length`` puts one
count per floc in the bin for its length however long it is,
``floc_frequency_per_m`` divides those by the analysed length, and
``normalized_count_shares`` turns them into percentages of the floc population.
These are what the figure draws, because "how often does a floc this long
happen" is the question a reader brings to a floc distribution.
"""

from typing import NamedTuple

import numpy as np

from utils.filters import bandpass_filter
from utils.plot_formatting import unit_label
import settings


def high_pass(values, cutoff_1m, fs):
    """The signal with everything slower than the cutoff taken out.

    A floc is a local excursion, so what counts as beyond the limit has to be
    measured against the sheet around it and not against the mean of the whole
    roll. Slow variation - roll periodicity, drift, a profile tilt - would
    otherwise push whole stretches past the limit and have them counted as one
    enormous floc.

    The filter is the application's own band pass with its high edge left at
    the usable Nyquist, so a trace filtered here is the trace the other windows
    would draw for the same setting. Mean correction is off because the result
    is meant to be mean free: the limits are deviations, not levels.
    """
    values = np.asarray(values, dtype=float).reshape(-1)
    high_edge = usable_high_edge(fs)

    if not (0 < cutoff_1m < high_edge) or len(values) < 4:
        # No usable band: centre the data and leave it otherwise untouched
        # rather than returning a flat line, which would report no flocs at all.
        finite = values[np.isfinite(values)]
        return values - (float(np.mean(finite)) if len(finite) else 0.0)

    return np.asarray(
        bandpass_filter(values, cutoff_1m, high_edge, fs, correct_mean=False),
        dtype=float).reshape(-1)


def usable_high_edge(fs):
    """The top of the band the FIR filter can pass, as the band pass controls use it."""
    return (fs / 2) * ((settings.FILTER_NUMTAPS - 1) / settings.FILTER_NUMTAPS)


def exceedance_run_lengths(values, limit):
    """Lengths, in samples, of the contiguous stretches beyond the limit.

    A positive limit looks for stretches above it and a negative one for
    stretches below it, so the same function serves all four limits.
    """
    values = np.asarray(values, dtype=float).reshape(-1)
    if len(values) == 0:
        return np.zeros(0, dtype=int)

    beyond = values > limit if limit >= 0 else values < limit
    beyond &= np.isfinite(values)
    if not beyond.any():
        return np.zeros(0, dtype=int)

    # Padding with False at both ends turns every run into exactly one rising
    # and one falling edge, including runs that touch the ends of the data.
    padded = np.concatenate(([False], beyond, [False]))
    edges = np.flatnonzero(np.diff(padded.astype(np.int8)))
    return edges[1::2] - edges[0::2]


def size_shares(run_lengths, total_samples, bin_count=None):
    """Share of the whole analysed length held by flocs of each length, in percent.

    Floc length is quantised by the sample step - a floc is a whole number of
    samples long - so each bin is one sample count and no binning choice is
    imposed on the data. Bin k holds flocs of exactly k samples; the last bin
    collects everything longer, weighted by its true length so that the
    percentages still add up to the share of the length that is beyond the
    limit.

    These are the absolute shares, and their sum is ``exceeded_percent``. That
    is what makes them worth keeping on their own: the figure normalises them,
    but how much of the sheet is floc is read from here.
    """
    bin_count = int(settings.FLOC_BIN_COUNT if bin_count is None else bin_count)
    shares = np.zeros(max(bin_count, 0), dtype=float)
    run_lengths = np.asarray(run_lengths, dtype=int).reshape(-1)
    if total_samples <= 0 or bin_count < 1 or len(run_lengths) == 0:
        return shares

    bins = np.clip(run_lengths, 1, bin_count) - 1
    occupied = np.bincount(bins, weights=run_lengths.astype(float),
                           minlength=bin_count)
    return 100.0 * occupied[:bin_count] / float(total_samples)


def normalize_shares(shares):
    """The same shares scaled to add up to 100 %, or zeros when there is nothing.

    Dividing by a total of zero is how an empty result would turn into NaNs and
    an empty axis, so a limit that caught no flocs is answered with a flat line
    at zero instead.
    """
    shares = np.asarray(shares, dtype=float)
    total = float(np.sum(shares))
    if not np.isfinite(total) or total <= 0.0:
        return np.zeros_like(shares)
    return 100.0 * shares / total


def normalized_size_shares(run_lengths, total_samples, bin_count=None):
    """How the floc covered length divides between floc lengths, in percent.

    The same length weighted distribution as ``size_shares``, measured against
    the flocs themselves rather than against the sheet, so the bins add up to
    100 % whenever at least one floc was found. That is what a reader expects
    of something called a distribution, and it lets the shape be compared
    between limits without each limit's coverage setting the height of its
    curve.

    It stays a distribution of length rather than of counts: a bin holds the
    length that the flocs of that length occupy, so one long floc weighs as
    much as the many short ones that fill the same stretch of paper.
    """
    return normalize_shares(size_shares(run_lengths, total_samples, bin_count))


def floc_counts_by_length(run_lengths, bin_count=None):
    """How many flocs fall in each length bin.

    Bin k holds the flocs of exactly k samples. The last bin holds every floc
    at least that long, and this is where a count parts company with a length:
    a floc ten times the last bin's length is still one floc, where
    ``size_shares`` would give it ten times the weight.
    """
    bin_count = int(settings.FLOC_BIN_COUNT if bin_count is None else bin_count)
    counts = np.zeros(max(bin_count, 0), dtype=int)
    run_lengths = np.asarray(run_lengths, dtype=int).reshape(-1)
    if bin_count < 1 or len(run_lengths) == 0:
        return counts

    bins = np.clip(run_lengths, 1, bin_count) - 1
    return np.bincount(bins, minlength=bin_count)[:bin_count].astype(int)


def floc_frequency_per_m(run_lengths, analysed_length_m, bin_count=None):
    """How often a floc of each length happens, per metre of analysed paper.

    The bins add up to ``flocs_per_m``, so the height of the distribution and
    the total in the table are the same number read two ways, and a value can
    be taken off the axis as it stands rather than as a share of something.
    """
    counts = floc_counts_by_length(run_lengths, bin_count)
    analysed_length_m = float(analysed_length_m)
    if not np.isfinite(analysed_length_m) or analysed_length_m <= 0.0:
        return np.zeros(len(counts), dtype=float)
    return counts.astype(float) / analysed_length_m


def normalized_count_shares(run_lengths, bin_count=None):
    """What percentage of the detected flocs each length bin holds.

    Accumulated, this is the curve that answers "what fraction of the flocs are
    this long or shorter", and it reaches 100 % whenever a floc was found. With
    no flocs there is nothing to divide by, so the answer is zeros rather than
    NaNs.
    """
    counts = floc_counts_by_length(run_lengths, bin_count)
    total = float(counts.sum())
    if total <= 0.0:
        return np.zeros(len(counts), dtype=float)
    return 100.0 * counts.astype(float) / total


def bin_lengths_mm(sample_step, bin_count=None):
    """The floc length each bin stands for, in mm.

    A floc is a whole number of samples long, so bin k is not a range but one
    length exactly: k sample steps. Drawing it half a step short of that, as
    the legacy axis did, reads as a floc length the sampling cannot produce.

    The last bin also holds every longer floc, which is why the figure marks
    its tick as open ended rather than as the single length the others are.
    """
    bin_count = int(settings.FLOC_BIN_COUNT if bin_count is None else bin_count)
    return np.arange(1, bin_count + 1) * 1000.0 * sample_step


def bin_centres_mm(sample_step, bin_count=None):
    """The former name of :func:`bin_lengths_mm`, kept for callers outside this repository.

    There is no centre to speak of: the bins are single lengths, not ranges.
    """
    return bin_lengths_mm(sample_step, bin_count)


def visible_bin_count(occupancy_per_limit, bin_count=None):
    """How many bins are worth drawing: the occupied ones, plus one.

    A floc cannot outlast about half the longest wavelength the high pass lets
    through, so on a coarse sample step most of the axis can never hold
    anything at all, and drawing all of it squeezes the whole distribution into
    the first centimetre of the panel. Every bin is still calculated - this
    only says where a view may stop, and only where every limit is empty.

    ``occupancy_per_limit`` is one array per limit - counts, frequencies or
    length shares alike, since only which bins are non-zero matters.
    """
    bin_count = int(settings.FLOC_BIN_COUNT if bin_count is None else bin_count)
    occupied = [int(np.max(np.nonzero(bins)[0]))
                for bins in (np.asarray(one, dtype=float).reshape(-1)
                             for one in occupancy_per_limit)
                if np.any(bins)]
    if not occupied:
        return bin_count
    return min(bin_count, max(occupied) + 2)


class LengthAxis(NamedTuple):
    """Where the ticks of a floc length axis go, and how they are written."""
    tick_step: float
    decimals: int
    open_bin: float


def length_axis_ticks(lengths, sample_step, visible=None):
    """The tick step, the decimals, and the open ended bin if it is in view.

    Ticks fall on whole numbers of sample steps, because those are the only
    floc lengths the data can contain, and they carry a decimal where a sample
    step does not divide into whole millimetres - a 12.8 mm bin must not read
    as 13. ``open_bin`` is the length of the last bin, which stands for every
    floc at least that long rather than for one length, and is None when the
    view stops short of it.
    """
    lengths = np.asarray(lengths, dtype=float).reshape(-1)
    step_mm = 1000.0 * float(sample_step)
    visible = len(lengths) if visible is None else int(visible)
    stride = max(1, int(round(visible / 6)))
    tick_step = stride * step_mm
    decimals = 0 if abs(tick_step - round(tick_step)) < 0.05 else 1
    open_bin = float(lengths[-1]) if visible >= len(lengths) else None
    return LengthAxis(tick_step, decimals, open_bin)


def floc_statistics(run_lengths, total_samples, sample_step):
    """Exceeded share, mean floc length and floc count, as the legacy table gives them.

    ``mean_size_mm`` is the mean floc length. The key keeps its old name
    because the report library reads it.
    """
    run_lengths = np.asarray(run_lengths, dtype=int).reshape(-1)
    analysed_length_m = total_samples * sample_step
    if total_samples <= 0:
        return {"count": 0, "exceeded_percent": np.nan,
                "mean_size_mm": np.nan, "flocs_per_m": np.nan}

    return {
        "count": int(len(run_lengths)),
        "exceeded_percent": 100.0 * float(run_lengths.sum()) / float(total_samples),
        "mean_size_mm": (1000.0 * sample_step * float(run_lengths.mean())
                         if len(run_lengths) else np.nan),
        "flocs_per_m": (len(run_lengths) / analysed_length_m
                        if analysed_length_m > 0 else np.nan),
    }


def threshold_label(limit, unit=""):
    """A limit written as the condition it is, for a figure to show.

    ``Limit++`` is a serviceable identifier inside the code and says nothing to
    a reader of the plot; ``> +2 g/m²`` says exactly what was counted. The
    names stay where they earn their keep - keying colours, saved attributes -
    and this is what the legend and the table show instead.
    """
    limit = float(limit)
    condition = f"< {limit:.3g}" if limit < 0 else f"> +{limit:.3g}"
    return f"{condition} {unit_label(unit)}".strip()


def limit_set(limit):
    """The four limits the tool reports, derived from the one that is entered.

    Ordered as the legacy table orders them, strongest positive first, so a
    figure legend and a table read top to bottom the same way.
    """
    limit = abs(float(limit))
    return [
        ("Limit++", 2.0 * limit),
        ("Limit+", limit),
        ("Limit-", -limit),
        ("Limit--", -2.0 * limit),
    ]


class FlocResult(NamedTuple):
    """One limit's answer, with each field named for what it counts.

    The first two are the curves the figure draws, and both are about the
    population of flocs. ``frequency_per_m`` is how often a floc of each length
    happens per metre, and sums to ``statistics["flocs_per_m"]``.
    ``cumulative_count_percent`` accumulates the same counts as percentages of
    the flocs found, and reaches 100 % whenever there was one.

    ``counts`` is the raw floc count per bin behind both. ``length_shares`` is
    the other family entirely - the share of the whole analysed length that
    the flocs of each length occupy, summing to
    ``statistics["exceeded_percent"]`` - kept because how much paper is
    affected is a different question from how many flocs there are, and the
    table answers it.

    The statistics dictionary carries the limit itself, so a caller can label
    the result without being handed it twice.
    """
    frequency_per_m: np.ndarray
    cumulative_count_percent: np.ndarray
    statistics: dict
    counts: np.ndarray
    length_shares: np.ndarray


def floc_distribution(profiles, sample_step, limit, cutoff_1m,
                      bin_count=None, already_filtered=False):
    """The whole calculation for one limit, over one or more profiles.

    ``profiles`` is a list because a CD analysis has one profile per sample.
    Each profile is filtered and thresholded on its own, so that no floc is
    counted across a profile boundary, and the shares are then taken over their
    pooled length.
    """
    fs = 1.0 / sample_step
    filtered = [np.asarray(profile, dtype=float).reshape(-1) if already_filtered
                else high_pass(profile, cutoff_1m, fs)
                for profile in profiles]
    total_samples = int(sum(len(profile) for profile in filtered))

    runs = (np.concatenate([exceedance_run_lengths(profile, limit)
                            for profile in filtered]).astype(int)
            if filtered else np.zeros(0, dtype=int))

    analysed_length_m = total_samples * sample_step
    counts = floc_counts_by_length(runs, bin_count)
    frequency = floc_frequency_per_m(runs, analysed_length_m, bin_count)
    count_shares = normalized_count_shares(runs, bin_count)
    statistics = floc_statistics(runs, total_samples, sample_step)
    statistics["limit"] = float(limit)
    return FlocResult(frequency, np.cumsum(count_shares), statistics, counts,
                      size_shares(runs, total_samples, bin_count))
