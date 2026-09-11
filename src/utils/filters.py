from scipy.signal import firwin, fftconvolve
import numpy as np

from utils.signal_processing import interpolate_non_finite
import settings
import logging


def mirror_pad(data, numtaps):
    """
    Pads the data by mirroring at both ends.

    :param data: Array-like, the data to be padded.
    :param numtaps: int, the number of taps in the FIR filter.
    :return: Array-like, the padded data.
    """
    start_mirror = data[:numtaps][::-1]
    end_mirror = data[-numtaps:][::-1]
    return np.concatenate((start_mirror, data, end_mirror))


def _band_kind(lowcut, highcut, fs):
    """What a band asks for: "low", "high", "band", "all", or None when empty.

    A band from zero is a low pass and a band reaching the Nyquist frequency a
    high pass. Built as a band pass with its lower edge a hair above zero, a
    low pass would leave the level and the longest waves on the slope of that
    edge instead of passing them whole.
    """
    nyquist = fs / 2.0
    low = max(0.0, float(lowcut))
    high = min(float(highcut), nyquist)
    if not low < high:
        return None
    reaches_nyquist = high >= nyquist * (1 - 0.0001)
    if low <= 0:
        return "all" if reaches_nyquist else "low"
    return "high" if reaches_nyquist else "band"


def filter_numtaps(lowcut, highcut, fs, data_length, numtaps=settings.FILTER_NUMTAPS):
    """The length of the filter for a band: odd, and adapted to the band.

    A windowed FIR filter tells frequencies apart about as finely as it holds
    periods of them, so a length that is plenty for a cutoff at 10 1/m cannot
    separate 0.05 1/m from 0.2 1/m at all. The filter spans at least
    FILTER_CUTOFF_CYCLES periods of its lowest cutoff and never fewer than
    ``numtaps`` samples. It is odd, so that its delay is a whole sample and
    the output lines up with the input. Data too short for it get the longest
    filter they hold, with a warning, because a cutoff whose wavelength the
    data hold only a few times cannot be filtered sharply.
    """
    nyquist = fs / 2.0
    cutoffs = [float(cut) for cut in (lowcut, highcut) if 0 < float(cut) < nyquist]
    wanted = int(numtaps)
    if cutoffs:
        wanted = max(wanted, int(np.ceil(settings.FILTER_CUTOFF_CYCLES * fs / min(cutoffs))))
    wanted |= 1
    longest = max(3, data_length if data_length % 2 else data_length - 1)
    if wanted <= longest:
        return wanted
    logging.warning(
        "Data length too small for filter length: a %.4g 1/m cutoff needs %d samples "
        "and the data have %d, so a %d tap filter is used.",
        min(cutoffs) if cutoffs else float(highcut), wanted, data_length, longest)
    return longest


def _coefficients(kind, lowcut, highcut, fs, numtaps, window):
    """FIR coefficients for a band of the given kind."""
    low = max(0.0, float(lowcut))
    high = min(float(highcut), fs / 2.0)
    if kind == "low":
        coefficients = firwin(numtaps, high, fs=fs)
    elif kind == "high":
        coefficients = firwin(numtaps, low, pass_zero=False, fs=fs)
    else:
        coefficients = firwin(numtaps, [low, high], pass_zero=False, fs=fs)

    if window == "hamming":
        coefficients = coefficients * np.hamming(numtaps)
    if kind == "low":
        # The second window takes a little off the gain at zero; a low pass
        # passes the level and the longest waves whole.
        coefficients = coefficients / np.sum(coefficients)

    return coefficients


def _warn_degenerate_band(lowcut, highcut, fs):
    logging.warning(
        "Band pass range [%s, %s] 1/m is not a valid band at fs=%s; returning mean level.",
        lowcut, highcut, fs)


def bandpass_filter_columns(data, lowcut, highcut, fs, numtaps=settings.FILTER_NUMTAPS,
                            window="hamming", mirror=True, correct_mean=True):
    """Apply the same band pass filter to every column of a 2D array.

    Equivalent to calling bandpass_filter() on each column, but the filter
    coefficients are built once and all columns go through a single FFT
    convolution, which is substantially faster than one transform per channel.

    :param data: 2D array, samples along axis 0 and channels along axis 1.
    :return: Filtered array of the same shape.
    """
    values = np.asarray(data, dtype=float)
    if values.ndim == 1:
        return bandpass_filter(values, lowcut, highcut, fs, numtaps=numtaps,
                               window=window, mirror=mirror,
                               correct_mean=correct_mean).reshape(-1, 1)

    data_length, channel_count = values.shape
    if data_length < 4 or channel_count == 0:
        return values.copy()

    filled = np.empty_like(values)
    for index in range(channel_count):
        filled[:, index], _ = interpolate_non_finite(
            values[:, index], context="band pass filter input")

    original_means = filled.mean(axis=0)

    kind = _band_kind(lowcut, highcut, fs)
    if kind is None:
        _warn_degenerate_band(lowcut, highcut, fs)
        return np.broadcast_to(original_means, values.shape).copy()
    if kind == "all":
        return filled

    numtaps = filter_numtaps(lowcut, highcut, fs, data_length, numtaps)
    coefficients = _coefficients(kind, lowcut, highcut, fs, numtaps, window)

    padded = filled
    if mirror:
        padded = np.concatenate(
            (filled[:numtaps][::-1], filled, filled[-numtaps:][::-1]), axis=0)

    # Transpose so each channel is a contiguous row: transforming along the
    # fastest varying axis is markedly quicker than striding down columns.
    padded = np.ascontiguousarray(padded.T)
    filtered = fftconvolve(padded, coefficients[None, :], mode='same', axes=1).T

    if mirror:
        filtered = filtered[numtaps:-numtaps]

    if correct_mean:
        filtered = filtered - filtered.mean(axis=0) + original_means

    return filtered


def bandpass_filter(data, lowcut, highcut, fs, numtaps=settings.FILTER_NUMTAPS, window="hamming", mirror=True, use_epsilon=True, correct_mean=True):
    """
    Applies a phase-correct FIR bandpass filter with Hamming windowing.

    A band from zero is a low pass and a band reaching the Nyquist frequency a
    high pass. The filter is as long as its lowest cutoff needs and shortened
    to fit data that are shorter; see filter_numtaps.

    :param data: Array-like, the data to filter.
    :param lowcut: float, the low cutoff frequency.
    :param highcut: float, the high cutoff frequency.
    :param fs: float, the sampling rate.
    :param numtaps: int, the shortest filter; a low cutoff lengthens it.
    :param mirror: bool, optional, if set to True, pads the data with a mirrored copy.
    :return: Array-like, the filtered data.
    """

    data = np.asarray(data, dtype=float).reshape(-1)

    # Convolution is FFT based at these lengths, so a single non-finite sample
    # would turn the whole output into NaN. Fill gaps before filtering.
    data, _ = interpolate_non_finite(data, context="band pass filter input")

    data_length = len(data)
    if data_length < 4:
        return data.copy()

    original_mean = np.mean(data)

    kind = _band_kind(lowcut, highcut, fs)
    if kind is None:
        # Degenerate band (e.g. low == high). Return the mean level rather than
        # raising, so the caller still gets a well defined, clearly empty result.
        _warn_degenerate_band(lowcut, highcut, fs)
        return np.full(data_length, original_mean)
    if kind == "all":
        return data.copy()

    numtaps = filter_numtaps(lowcut, highcut, fs, data_length, numtaps)
    coefficients = _coefficients(kind, lowcut, highcut, fs, numtaps, window)

    # Pad the data with a mirrored copy if mirror is True
    if mirror:
        data = mirror_pad(data, numtaps)

    # A long filter over a long record is only practical through the FFT.
    filtered_data = fftconvolve(data, coefficients, mode='same')

    # Remove the mirrored padding if mirror is True
    if mirror:
        filtered_data = filtered_data[numtaps:-numtaps]

    if correct_mean:
        filtered_data = filtered_data - np.mean(filtered_data)
        filtered_data += original_mean

    return filtered_data
