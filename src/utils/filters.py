from scipy.signal import firwin, convolve, freqz, fftconvolve
import numpy as np
import matplotlib.pyplot as plt

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

    numtaps = _adjusted_numtaps(numtaps, data_length)
    coefficients = _bandpass_coefficients(lowcut, highcut, fs, numtaps, window)
    if coefficients is None:
        return np.broadcast_to(original_means, values.shape).copy()

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


def _adjusted_numtaps(numtaps, data_length):
    """Shrink the filter to fit short data, keeping the tap count odd."""
    if data_length >= numtaps:
        return numtaps

    new_numtaps = max(3, data_length - (data_length % 2) - 1)
    logging.warning(
        "Data length too small for filter length. Using smaller filter window length.")
    return new_numtaps


def _bandpass_coefficients(lowcut, highcut, fs, numtaps, window):
    """FIR band pass coefficients, or None when the band is degenerate."""
    epsilon = 0.0001
    nyquist = fs / 2.0
    low_edge = max(0.0, float(lowcut)) + epsilon
    high_edge = min(float(highcut), nyquist * (1 - epsilon))

    if not (0 < low_edge < high_edge < nyquist):
        logging.warning(
            "Band pass range [%s, %s] 1/m is not a valid band at fs=%s; returning mean level.",
            lowcut, highcut, fs)
        return None

    coefficients = firwin(numtaps, [low_edge, high_edge], pass_zero=False, fs=fs)
    if window == "hamming":
        coefficients = coefficients * np.hamming(numtaps)

    return coefficients


def bandpass_filter(data, lowcut, highcut, fs, numtaps=settings.FILTER_NUMTAPS, window="hamming", mirror=True, use_epsilon=True, correct_mean=True):
    """
    Applies a phase-correct FIR bandpass filter with Hamming windowing.
    The number of taps is automatically adjusted if the input data is too short.

    :param data: Array-like, the data to filter.
    :param lowcut: float, the low cutoff frequency.
    :param highcut: float, the high cutoff frequency.
    :param fs: float, the sampling rate.
    :param numtaps: int, the number of taps in the filter.
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

    # Adjust number of taps if data is too short
    if data_length < numtaps:
        # Calculate new number of taps that's smaller than data length
        # Keep it odd for FIR filter
        new_numtaps = data_length - (data_length % 2) - 1
        # Ensure we have at least 3 taps for a meaningful filter
        new_numtaps = max(3, new_numtaps)
        numtaps = new_numtaps
        logging.warning("Data length too small for filter length. Using smaller filter window length.")

    epsilon = 0.0001
    nyquist = fs / 2.0
    low_edge = max(0.0, float(lowcut)) + epsilon
    high_edge = min(float(highcut), nyquist * (1 - epsilon))
    if not (0 < low_edge < high_edge < nyquist):
        # Degenerate band (e.g. low == high). Return the mean level rather than
        # raising, so the caller still gets a well defined, clearly empty result.
        logging.warning(
            "Band pass range [%s, %s] 1/m is not a valid band at fs=%s; returning mean level.",
            lowcut, highcut, fs)
        return np.full(data_length, original_mean)

    # Pad the data with a mirrored copy if mirror is True
    if mirror:
        data = mirror_pad(data, numtaps)

    # Create the filter coefficients
    fir_coeff = firwin(numtaps, [low_edge, high_edge], pass_zero=False, fs=fs)

    if window == "hamming":
        hamming_window = np.hamming(numtaps)
        fir_coeff *= hamming_window

    if False:
        w, h = freqz(fir_coeff, worN=8000)
        # Convert w to cy/m
        freq = w * fs / (2 * np.pi)
        # Plot the magnitude response
        plt.figure(figsize=(12, 6))
        plt.subplot(2, 1, 1)
        plt.plot(freq, 20 * np.log10(np.abs(h)), 'b')
        plt.title('Filter Frequency Response')
        plt.xlabel('Frequency [Hz]')
        plt.ylabel('Gain [dB]')
        plt.grid()
        plt.xlim(0, fs / 2)
        plt.ylim(-100, 5)

        # Plot the phase response
        plt.subplot(2, 1, 2)
        angles = np.unwrap(np.angle(h))
        plt.plot(freq, angles, 'g')
        plt.ylabel('Angle (radians)')
        plt.xlabel('Frequency [Hz]')
        plt.grid()
        plt.xlim(0, fs / 2)
        plt.show()

    # Apply the filter
    filtered_data = convolve(data, fir_coeff, mode='same')

    # Remove the mirrored padding if mirror is True
    if mirror:
        filtered_data = filtered_data[numtaps:-numtaps]

    if correct_mean:
        filtered_data = filtered_data - np.mean(filtered_data)
        filtered_data += original_mean

    return filtered_data
