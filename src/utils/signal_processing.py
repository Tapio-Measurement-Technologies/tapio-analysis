import numpy as np
import scipy
import matplotlib.pyplot as plt
import settings

# NLS estimators for


def vandermonde(w, N):
    L = len(w)
    Z = np.exp(np.full((L, N), np.arange(N)).T * np.array(w) * 1j)
    return Z


def single_nls(x, w, L):
    L_array = np.arange(-L, L+1)
    L_array = L_array[L_array != 0]
    v_freqs = w * L_array
    Z = vandermonde(v_freqs, len(x))
    return (x.T @ Z @ np.linalg.inv(Z.T @ Z) @ Z.T @ x).real


def hs_units(x, Fs, w_initial, wrange, user_f_min, user_f_max, L=10):
    # Harmonic summation method for fundamental frequency estimation
    X = np.fft.fft(x)
    freqs = np.fft.fftfreq(len(x), 1/Fs)

    # Calculate the default f_min and f_max based on w_initial and wrange
    calculated_f_min = w_initial - wrange
    calculated_f_max = w_initial + wrange

    # Adjust f_min and f_max based on user-defined limits
    f_min = max(calculated_f_min, user_f_min)
    f_max = min(calculated_f_max, user_f_max)
    print(f_min)
    print(f_max)

    valid_indices = np.where((freqs >= f_min) & (freqs <= f_max))[0]

    max_sum = 0
    fundamental_freq = 0

    # Calculate the spacing between bins in frequency domain
    freq_spacing = Fs / len(x)

    for index in valid_indices:
        current_freq = freqs[index]
        harmonic_sums = np.abs(X[index])

        for harmonic in range(2, L+1):
            harmonic_freq = current_freq * harmonic
            if harmonic_freq < Fs / 2:
                # Calculate harmonic index directly based on the frequency and spacing
                harmonic_index = int(np.round(harmonic_freq / freq_spacing))
                if harmonic_index < len(X):
                    harmonic_sums += np.abs(X[harmonic_index])

        if harmonic_sums > max_sum:
            max_sum = harmonic_sums
            fundamental_freq = current_freq

    return fundamental_freq


def nls_units(x, Fs, w_initial, wrange=0.1, step=0.01, L=10):
    # Estimates the fundamental frequency within a range, will convert to units based on given Fs
    w_min = w_initial - wrange
    w_max = w_initial + wrange
    w_range = np.arange(w_min, w_max + step, step)

    max_nls = None
    max_w = None

    w_units_list = []  # To store w_units for plotting
    nls_values = []  # To store NLS values for plotting

    NLS_DEBUG = False
    for w_units in w_range:
        w = w_units / Fs * 2 * np.pi  # Convert to rad/sample for processing
        current_nls = single_nls(x, w, L)
        if max_nls is None or current_nls > max_nls:
            max_nls = current_nls
            max_w = w_units
        if NLS_DEBUG:
            print(f"{w_units:.2f}: {current_nls}")

        w_units_list.append(w_units)
        nls_values.append(current_nls)
    if NLS_DEBUG:
        plt.figure(figsize=(10, 6))
        plt.plot(w_units_list, nls_values, marker='.', linestyle='-')
        plt.xlabel('Frequency [units]')
        plt.ylabel('NLS Value')
        plt.title('NLS vs frequency')
        plt.grid(True)
        plt.show()

    return max_w  # Return the best frequency in Hz


def nls_rad(x, w_initial, L=10, wrange=0.1, step=0.01):
    w_min = (1 - wrange) * w_initial
    w_max = (1 + wrange) * w_initial
    w_range = np.arange(w_min, w_max + step, step)
    max_nls = None
    max_w = None
    for w in w_range:
        current_nls = single_nls(x, w, L)
        if max_nls is None or current_nls > max_nls:
            max_nls = current_nls
            max_w = w

    return max_w


def generate_sine_wave(freq, sample_rate, duration, amplitude=1.0):
    t = np.arange(0, duration, 1 / sample_rate)  # Time vector
    sine_wave = amplitude * np.sin(2 * np.pi * freq * t)
    return sine_wave


def harmonic_fitting_units(x, Fs, w):
    # Function to return single "mean revolution" using least squares harmonic model fitting
    # Called SOS analysis (Separate Original Signals)
    L = settings.SOS_HARMONICS
    w_rad = w / Fs * 2 * np.pi  # Convert to rad/sample for processing
    L_array = np.arange(-L, L+1)
    L_array = L_array[L_array != 0]
    v_freqs = w_rad * L_array
    Z = vandermonde(v_freqs, len(x))
    a_est, _, _, _ = scipy.linalg.lstsq(Z, x, lapack_driver="gelsy")
    # Reconstructing the signal using the harmonic model
    real_y = (Z @ a_est).real
    period_samples = int(Fs / w)
    return real_y[:period_samples]

def get_n_peaks(data, n, threshold = 0):
    """
    Get the top n maximum amplitudes and their corresponding frequencies from the data,
    considering only frequencies above a given threshold.

    Parameters:
    data (numpy.ndarray): A 2D array where the first column is frequencies and the second column is amplitudes.
    n (int): The number of maximum amplitudes to retrieve.
    threshold (float): The frequency threshold below which data points are ignored.

    Returns:
    numpy.ndarray: A 2D array containing the top n frequencies and their corresponding amplitudes.
    """
    # Filter the data based on the threshold
    filtered_data = data[data[:, 0] >= threshold]

    # Sort the array based on the amplitudes (second column)
    sorted_data = data[data[:, 1].argsort()]

    # Select the top n rows with the highest amplitudes
    top_n_data = sorted_data[-n:]

    # Reverse the order to have the highest amplitude first
    top_n_data = top_n_data[::-1]

    return top_n_data

if __name__ == "__main__":
    fs = 1000
    f = 5
    x = generate_sine_wave(5, fs, 20)
    # print(nls_units(x, fs, 4.95, 0.5, 0.01))

    x = harmonic_fitting_units(x, fs, 5)

    plt.plot(x)
    plt.show()
