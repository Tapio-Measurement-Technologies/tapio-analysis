import logging

import numpy as np
import scipy
import scipy.signal
import matplotlib.pyplot as plt
import settings

# NLS estimators for


def interpolate_non_finite(data, context=""):
    """Linearly interpolate NaN/Inf samples so they cannot poison FFT or FIR results.

    Convolution and FFT based routines spread a single non-finite sample across the
    whole output, so gaps are filled before any of them run. Samples outside the
    first and last finite value are filled with the nearest finite value.

    :param data: Array-like input signal.
    :param context: Optional label used in the log message.
    :return: (filled_data, number_of_samples_filled). Returns the input unchanged
             when it is all finite, and an all-zero array when nothing is finite.
    """
    values = np.asarray(data, dtype=float).reshape(-1)
    non_finite = ~np.isfinite(values)
    filled_count = int(np.count_nonzero(non_finite))

    if filled_count == 0:
        return values, 0

    if filled_count == len(values):
        logging.warning(
            "No finite samples available%s, using zeros.",
            f" in {context}" if context else "",
        )
        return np.zeros_like(values), filled_count

    indices = np.arange(len(values))
    values = values.copy()
    values[non_finite] = np.interp(
        indices[non_finite], indices[~non_finite], values[~non_finite])

    logging.warning(
        "Interpolated %d non-finite sample(s)%s.",
        filled_count,
        f" in {context}" if context else "",
    )
    return values, filled_count


def segment_count(data_length, nperseg, noverlap):
    """Number of Welch/spectrogram segments that fit in the data."""
    step = nperseg - noverlap
    if step <= 0 or data_length < nperseg:
        return 0
    return 1 + (data_length - nperseg) // step


def effective_segment_count(window, nperseg, noverlap, n_segments):
    """Number of *independent* segments represented by n_segments overlapping ones.

    Overlapping Welch segments share samples, so they are correlated and do not
    each contribute a full degree of freedom. The standard correction (Welch
    1967, Harris 1978) divides the segment count by

        1 + 2 * sum_m (1 - m/n) * c(m)^2

    where c(m) is the normalised autocorrelation of the analysis window at a
    shift of m segment steps. At the shipped 85% overlap this matters a lot: 77
    nominal segments are worth about 24 independent ones.

    :param window: Window name accepted by scipy.signal.get_window.
    :param nperseg: Segment length in samples.
    :param noverlap: Overlap in samples.
    :param n_segments: Nominal number of segments.
    :return: Effective segment count as a float (never more than n_segments).
    """
    if n_segments is None or n_segments < 1:
        return 0.0

    step = nperseg - noverlap
    if step <= 0:
        return 1.0

    try:
        values = scipy.signal.get_window(window, nperseg)
    except (ValueError, TypeError):
        values = np.asarray(window, dtype=float)

    energy = np.sum(values ** 2)
    if energy <= 0:
        return float(n_segments)

    correction = 1.0
    shift = 1
    while shift * step < nperseg and shift < n_segments:
        overlap_correlation = np.sum(
            values[:nperseg - shift * step] * values[shift * step:]) / energy
        correction += 2.0 * (1.0 - shift / n_segments) * overlap_correlation ** 2
        shift += 1

    return float(n_segments) / correction


def frequency_refinement_range(selected_freq, view_min, view_max):
    """Search window for refining a selected frequency.

    Returns (halfwidth, f_min, f_max). The window was previously a fixed
    fraction of the *visible axis span*, which is unrelated to the selected
    frequency: on a default MD view a peak at 0.03 1/m got a +/-0.39 1/m search,
    so the estimator wandered down to the lowest FFT bin and reported a
    wavelength longer than the sample. The window is therefore also capped to a
    fraction of the selected frequency, and the lower edge is kept strictly
    positive so a zero-frequency candidate (whose wavelength is 1/0) can never
    be returned.
    """
    if selected_freq is None or not np.isfinite(selected_freq) or selected_freq <= 0:
        return None, None, None

    view_span = max(0.0, float(view_max) - float(view_min))
    halfwidth = view_span * settings.FREQUENCY_REFINEMENT_VIEW_FRACTION
    halfwidth = min(halfwidth,
                    selected_freq * settings.FREQUENCY_REFINEMENT_MAX_RELATIVE)

    if halfwidth <= 0:
        halfwidth = selected_freq * settings.FREQUENCY_REFINEMENT_MAX_RELATIVE

    f_min = max(float(view_min), selected_freq - halfwidth)
    f_max = min(float(view_max), selected_freq + halfwidth) if view_max else selected_freq + halfwidth
    # Strictly positive: the DC bin has no wavelength.
    f_min = max(f_min, selected_freq * 0.5, np.finfo(float).tiny)

    return halfwidth, f_min, f_max


def max_nperseg_for_effective_segments(data_length, overlap_fraction, target_effective,
                                       window="hann", minimum_nperseg=64):
    """Largest segment length that still yields target_effective independent segments.

    Segment count falls monotonically as the segment grows, so this binary
    searches for the largest segment length meeting the target. Used to cap the
    coherence window-length control: whatever the user selects on the slider is
    then guaranteed to give a usable estimate, instead of silently collapsing to
    a single segment (where coherence is identically 1).

    :return: Segment length in samples, at least minimum_nperseg.
    """
    data_length = int(data_length)
    minimum_nperseg = max(4, int(minimum_nperseg))
    if data_length < minimum_nperseg:
        return max(2, data_length)

    best = minimum_nperseg
    low, high = minimum_nperseg, data_length
    while low <= high:
        candidate = (low + high) // 2
        noverlap = min(int(round(candidate * overlap_fraction)), candidate - 1)
        segments = segment_count(data_length, candidate, noverlap)
        effective = effective_segment_count(window, candidate, noverlap, segments)
        if effective >= target_effective:
            best = candidate
            low = candidate + 1
        else:
            high = candidate - 1

    return best


def coherence_significance_level(n_segments, confidence=None):
    """Magnitude-squared coherence below which the estimate is indistinguishable from zero.

    For nd independent segments and uncorrelated inputs the MSC estimate is
    distributed as 1 - (1 - g)**(nd - 1), so the critical level is
    1 - alpha**(1/(nd - 1)). Pass the *effective* segment count from
    effective_segment_count when the segments overlap. Returns None when there
    are too few segments for the level to be meaningful.
    """
    if confidence is None:
        confidence = getattr(settings, "COHERENCE_SIGNIFICANCE_LEVEL", 0.95)
    if n_segments is None or n_segments <= 1:
        return None
    alpha = 1.0 - confidence
    return 1.0 - alpha ** (1.0 / (n_segments - 1))


def safe_spectral_params(requested_nperseg, overlap_fraction, data_length, require_segment_shorter_than_data=False):
    """Return integer Welch/spectrogram parameters that SciPy will accept."""
    data_length = int(data_length)
    if data_length < 2:
        return None

    nperseg = int(round(requested_nperseg))
    if nperseg < 2:
        return None

    if require_segment_shorter_than_data and nperseg >= data_length:
        return None

    nperseg = min(nperseg, data_length)
    noverlap = int(round(nperseg * overlap_fraction))
    noverlap = max(0, min(noverlap, nperseg - 1))
    return nperseg, noverlap


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
    """Harmonic summation estimate of a fundamental frequency.

    Returns None when the search range contains no usable candidate, so that
    callers keep the frequency the user selected instead of substituting zero,
    which would make the derived wavelength 1/0.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    x, _ = interpolate_non_finite(x, context="frequency refinement")
    if len(x) < 2:
        return None

    X = np.fft.fft(x)
    freqs = np.fft.fftfreq(len(x), 1/Fs)

    # Calculate the default f_min and f_max based on w_initial and wrange
    calculated_f_min = w_initial - wrange
    calculated_f_max = w_initial + wrange

    # Adjust f_min and f_max based on user-defined limits
    f_min = max(calculated_f_min, user_f_min)
    f_max = min(calculated_f_max, user_f_max)
    valid_indices = np.where((freqs >= f_min) & (freqs <= f_max))[0]

    max_score = None
    fundamental_freq = None

    # Calculate the spacing between bins in frequency domain
    freq_spacing = Fs / len(x)

    for index in valid_indices:
        current_freq = freqs[index]
        if current_freq <= 0:
            # A zero or negative candidate is not a fundamental, and returning
            # one would make the reported wavelength 1/0.
            continue

        harmonic_sums = np.abs(X[index])
        harmonics_used = 1

        for harmonic in range(2, L+1):
            harmonic_freq = current_freq * harmonic
            if harmonic_freq < Fs / 2:
                # Calculate harmonic index directly based on the frequency and spacing
                harmonic_index = int(np.round(harmonic_freq / freq_spacing))
                if harmonic_index < len(X):
                    harmonic_sums += np.abs(X[harmonic_index])
                    harmonics_used += 1

        # Normalise by the number of harmonics actually summed. Without this a
        # candidate at f/2 inherits the whole peak at f as its second harmonic,
        # plus room for more harmonics below Nyquist, and wins - so a 10 1/m
        # peak refines to 5 1/m whenever the search range is wide enough.
        score = harmonic_sums / harmonics_used

        if max_score is None or score > max_score:
            max_score = score
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


def harmonic_fitting_units(x, Fs, w, n_points=None):
    """Mean revolution at frequency w, by least-squares harmonic model fitting.

    Used by the SOS (Separate Original Signals) analysis. The model is a sum of
    complex exponentials at +/- k*w for k = 1..L, with no DC term, so the result
    is mean free.

    Rather than forming the full N x 2L design matrix and calling a dense least
    squares solver, this builds the 2L x 2L normal equations directly. The Gram
    matrix Z^H Z has a closed form - each entry is a Dirichlet kernel sum of a
    geometric series - and Z^H x is a set of 2L direct sums. That turns an
    O(N * L^2) factorisation of a 250k-row matrix into O(N * L) accumulation
    plus a 2L x 2L solve, which is what makes the analysis interactive.

    The reconstruction is evaluated on an evenly spaced angular grid covering
    exactly one full revolution. The previous version returned int(Fs/w) samples
    of the fitted signal, which is less than a whole period whenever Fs/w is not
    an integer, and then stretched that partial revolution over 360 degrees - a
    10% angular error at 10 1/m with MD sampling.

    :param x: Array-like signal.
    :param Fs: Sampling frequency in samples per unit distance.
    :param w: Fundamental frequency in the same units as Fs.
    :param n_points: Number of points in the returned revolution.
    :return: Real array of length n_points, one full revolution, mean free.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    x, _ = interpolate_non_finite(x, context="SOS input")

    if len(x) == 0 or w == 0 or not np.isfinite(w):
        return np.array([])

    L = int(settings.SOS_HARMONICS)
    if n_points is None:
        n_points = int(getattr(settings, "SOS_REVOLUTION_POINTS", 720))
    n_points = max(8, int(n_points))

    N = len(x)
    w_rad = w / Fs * 2 * np.pi  # rad/sample

    harmonics = np.arange(-L, L + 1)
    harmonics = harmonics[harmonics != 0]
    frequencies = w_rad * harmonics  # rad/sample, length 2L

    # Z^H x, without materialising the N x 2L design matrix. Only the L positive
    # harmonics are summed: x is real, so the negative harmonic sums are their
    # complex conjugates. Powers of the fundamental phasor are built by repeated
    # multiplication, so this touches one N-length array at a time instead of
    # allocating an N x 2L complex block.
    n = np.arange(N)
    phasor = np.exp(-1j * w_rad * n)
    running = np.ones(N, dtype=complex)
    positive_sums = np.empty(L, dtype=complex)
    for index in range(L):
        running *= phasor
        positive_sums[index] = running @ x

    ZHx = np.concatenate((np.conj(positive_sums[::-1]), positive_sums))

    # Z^H Z in closed form: entry (j, k) is sum_n exp(i*(w_k - w_j)*n), a
    # geometric series. The delta == 0 diagonal (and any aliased coincidences)
    # sum to N.
    delta = frequencies[None, :] - frequencies[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        denominator = 1.0 - np.exp(1j * delta)
        gram = (1.0 - np.exp(1j * delta * N)) / denominator
    coincident = np.abs(denominator) < 1e-12
    gram[coincident] = N

    # Small ridge term keeps the solve stable when two harmonics alias onto each
    # other (w close to a submultiple of Fs) and the Gram matrix goes singular.
    gram += np.eye(len(frequencies)) * (N * 1e-10)

    try:
        coefficients = np.linalg.solve(gram, ZHx)
    except np.linalg.LinAlgError:
        coefficients, *_ = np.linalg.lstsq(gram, ZHx, rcond=None)

    # Evaluate one full revolution on an angular grid: phase = 2*pi*k*theta.
    theta = np.linspace(0.0, 2 * np.pi, n_points, endpoint=False)
    basis = np.exp(1j * np.outer(theta, harmonics))
    return (basis @ coefficients).real

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
    sorted_data = filtered_data[filtered_data[:, 1].argsort()]

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
