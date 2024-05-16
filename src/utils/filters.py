from scipy.signal import firwin, convolve, freqz
import numpy as np
import matplotlib.pyplot as plt


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


def bandpass_filter(data, lowcut, highcut, fs, numtaps=300, window="hamming", mirror=True, use_epsilon=True, correct_mean=True):
    """
    Applies a phase-correct FIR bandpass filter with Hamming windowing.

    :param data: Array-like, the data to filter.
    :param lowcut: float, the low cutoff frequency.
    :param highcut: float, the high cutoff frequency.
    :param fs: float, the sampling rate.
    :param numtaps: int, the number of taps in the filter.
    :param mirror: bool, optional, if set to True, pads the data with a mirrored copy.
    :return: Array-like, the filtered data.
    """

    original_mean = np.mean(data)

    epsilon = 0.0001
    # Pad the data with a mirrored copy if mirror is True
    if mirror:
        data = mirror_pad(data, numtaps)

    # Create the filter coefficients
    fir_coeff = firwin(numtaps, [epsilon+lowcut, highcut], pass_zero=False, fs=fs)

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
