"""The floc distribution calculation: filtering, run detection, binning.

Kept apart from the analysis window so that the numbers behind a floc figure
can be computed - and tested - without a GUI, and so that anything else that
needs them (a report, a comparison script) uses this code rather than a copy
of it.

A floc, here, is one contiguous run of samples beyond a limit in the high pass
filtered signal, and what is measured of it is its length along the sample.

Two ways of counting that length live here and neither replaces the other.
``size_shares`` measures the flocs against the whole analysed length, which
answers how much of the sheet is floc. ``normalized_size_shares`` measures them
against each other, which answers how the floc covered length divides between
short and long flocs - the distribution the figure draws.
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
    """One limit's answer: the distribution, its cumulative and the statistics.

    ``shares`` and ``cumulative`` are normalised within the detected flocs, so
    the cumulative ends at 100 % whenever a floc was found; those are the
    curves the figure draws. ``absolute_shares`` is the same length weighted
    distribution measured against the whole analysed length, and its sum is
    ``statistics["exceeded_percent"]``. The statistics dictionary carries the
    limit itself, so a caller can label the result without being handed it
    twice.
    """
    shares: np.ndarray
    cumulative: np.ndarray
    statistics: dict
    absolute_shares: np.ndarray


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

    absolute_shares = size_shares(runs, total_samples, bin_count)
    shares = normalize_shares(absolute_shares)
    statistics = floc_statistics(runs, total_samples, sample_step)
    statistics["limit"] = float(limit)
    return FlocResult(shares, np.cumsum(shares), statistics, absolute_shares)
