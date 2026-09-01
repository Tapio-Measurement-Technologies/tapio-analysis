"""Numerical regression tests for the analysis calculations.

Each test pins a quantity to an independently derived answer (an analytic value,
or a deliberately naive reference implementation) so that a change in scaling,
units or convention fails loudly instead of silently altering reported
measurements.
"""

import numpy as np
import pandas as pd
import pytest

import settings
from analyses import (cepstrum, coherence, correlation_matrix, formation,
                      spectrogram, spectrum, time_domain)
from gui.components import StatsWidget
from utils.filters import bandpass_filter, bandpass_filter_columns
from utils.measurement import Measurement, drop_unusable_channels
from utils.report_generator import stats_for_report
from utils.signal_processing import (coherence_significance_level,
                                     frequency_refinement_range,
                                     harmonic_fitting_units, hs_units,
                                     interpolate_non_finite, segment_count)

SAMPLE_STEP = 0.0128
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


def sine(length, frequency, amplitude=1.0, offset=0.0, sample_step=SAMPLE_STEP):
    distances = np.arange(length) * sample_step
    return offset + amplitude * np.sin(2 * np.pi * frequency * distances)


# --------------------------------------------------------------------------
# Spectrum / spectrogram amplitude scaling
# --------------------------------------------------------------------------

def test_spectrum_reports_zero_to_peak_amplitude(qt_app):
    """sqrt(2*Pxx) with scaling='spectrum' is the zero-to-peak amplitude."""
    amplitude = 3.0
    nperseg = 5000
    frequency = 200 * FS / nperseg  # exactly on a bin centre
    measurement = md_measurement({"BW": sine(100000, frequency, amplitude, 100.0)})

    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = nperseg
    controller.auto_detect_peaks = False
    controller.plot()

    peak = controller.amplitudes[np.argmin(np.abs(controller.frequencies - frequency))]
    assert peak == pytest.approx(amplitude, rel=0.01)


@pytest.mark.parametrize("nperseg", [5000, 20000])
def test_spectrogram_amplitude_matches_spectrum_and_is_window_independent(qt_app, nperseg):
    """The spectrogram returns a PSD density; without the density-to-spectrum
    correction its amplitude is off by sqrt(ENBW) and changes with nperseg."""
    amplitude = 3.0
    frequency = 200 * FS / 5000
    measurement = md_measurement({"BW": sine(100000, frequency, amplitude, 100.0)})

    controller = spectrogram.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = nperseg
    controller.plot()

    row = np.argmin(np.abs(controller.frequencies - frequency))
    assert float(np.mean(controller.amplitudes[row, :])) == pytest.approx(amplitude, rel=0.03)


def test_spectrogram_color_scale_modes(qt_app, monkeypatch):
    measurement = md_measurement({"BW": sine(50000, 3.125, 3.0, 100.0)})
    controller = spectrogram.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.plot()

    amplitudes = controller.amplitudes
    monkeypatch.setattr(settings, "SPECTROGRAM_COLOR_SCALE_MODE", "relative")
    monkeypatch.setattr(settings, "SPECTROGRAM_COLOR_SCALE_FACTOR", 3.0)
    _, vmax, mode = controller.get_color_limits(amplitudes)
    assert mode == "relative"
    assert vmax == pytest.approx(3.0 * float(np.mean(amplitudes)))

    monkeypatch.setattr(settings, "SPECTROGRAM_COLOR_SCALE_MODE", "fixed")
    monkeypatch.setattr(settings, "SPECTROGRAM_FIXED_CLIM", {controller.channel: (0.0, 7.0)})
    vmin, vmax, mode = controller.get_color_limits(amplitudes)
    assert (vmin, vmax, mode) == (0.0, 7.0, "fixed")


def test_spectrogram_stats_table_reports_wavelength_in_cm(qt_app):
    measurement = md_measurement({"BW": sine(50000, 3.125, 3.0, 100.0)})
    controller = spectrogram.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.plot()
    controller.selected_freqs = [2.0]

    rendered = " ".join(cell for row in controller.getStatsTableData() for cell in row)
    assert "50.00 cm" in rendered  # 1/2 m = 50 cm
    assert "50.00 m" not in rendered


# --------------------------------------------------------------------------
# Coherence
# --------------------------------------------------------------------------

def test_segment_count_and_significance_level():
    assert segment_count(9807, 5000, 4250) == 7
    assert segment_count(9807, 9807, 8336) == 1
    # 1 - alpha ** (1/(nd-1)) for alpha = 0.05
    assert coherence_significance_level(7) == pytest.approx(1 - 0.05 ** (1 / 6))
    assert coherence_significance_level(1) is None


@pytest.mark.parametrize("requested_nperseg", [9807, 20000])
def test_coherence_caps_segment_length_instead_of_collapsing(qt_app, requested_nperseg):
    """With one Welch segment the magnitude-squared coherence is identically 1,
    so the window length is capped to what the data can actually support."""
    rng = np.random.default_rng(0)
    length = 9807
    measurement = md_measurement({"A": rng.normal(size=length),
                                  "B": rng.normal(size=length)})

    controller = coherence.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.channel, controller.channel2 = "A", "B"
    controller.nperseg = requested_nperseg
    controller.plot()

    assert controller.nperseg < length
    assert controller.n_segments >= settings.COHERENCE_MIN_SEGMENTS
    assert controller.effective_segments >= settings.COHERENCE_TARGET_EFFECTIVE_SEGMENTS
    # Uncorrelated channels must not come out as perfectly coherent.
    assert controller.amplitudes.max() < 0.95
    assert controller.amplitudes.mean() < 0.25


def test_coherence_refuses_when_too_few_segments(qt_app):
    """The guard still exists for data too short to average over."""
    rng = np.random.default_rng(0)
    length = 400
    measurement = md_measurement({"A": rng.normal(size=length),
                                  "B": rng.normal(size=length)})

    controller = coherence.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.channel, controller.channel2 = "A", "B"
    controller.nperseg = length
    controller.overlap = 0.0
    controller.spectrum_length_slider_min = length
    controller.plot()

    assert controller.n_segments < settings.COHERENCE_MIN_SEGMENTS
    assert len(controller.amplitudes) == 0


def test_coherence_of_uncorrelated_channels_stays_below_significance(qt_app):
    rng = np.random.default_rng(1)
    length = 200000
    measurement = md_measurement({"A": rng.normal(size=length),
                                  "B": rng.normal(size=length)})

    controller = coherence.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.channel, controller.channel2 = "A", "B"
    controller.nperseg = 4000
    controller.plot()

    assert controller.n_segments >= settings.COHERENCE_MIN_SEGMENTS
    assert controller.significance_level is not None
    below = np.mean(controller.amplitudes < controller.significance_level)
    assert below > 0.9, f"only {below:.1%} of bins below the significance line"


def test_coherence_export_column_is_dimensionless(qt_app):
    rng = np.random.default_rng(2)
    measurement = md_measurement({"A": rng.normal(size=50000),
                                  "B": rng.normal(size=50000)})
    controller = coherence.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.channel, controller.channel2 = "A", "B"
    controller.nperseg = 4000
    controller.plot()

    columns = list(controller.getExportData().columns)
    assert any("coherence" in name.lower() for name in columns)
    assert not any("amplitude" in name.lower() for name in columns)


# --------------------------------------------------------------------------
# Frequency refinement must never yield an unusable frequency
# --------------------------------------------------------------------------

def test_hs_units_returns_none_when_no_candidate():
    """A zero return made refineFrequency store 0 and refresh() divide 1/0."""
    values = sine(20000, 5.0, offset=100.0)
    # Search window that contains no FFT bin at all.
    assert hs_units(values, FS, 5.0, 1e-9, 5.0 + 1e-6, 5.0 + 2e-6) is None
    assert hs_units(np.array([1.0]), FS, 5.0, 1.0, 0.0, 30.0) is None


def test_hs_units_does_not_lock_onto_a_subharmonic():
    """Normalising by the harmonic count stops f/2 from winning on f's peak."""
    values = sine(200000, 10.0, offset=100.0)
    for search_half_width in (3.0, 6.0, 9.0):
        refined = hs_units(values, FS, 10.0, search_half_width, 0.0, FS / 2)
        assert refined == pytest.approx(10.0, abs=0.05), \
            f"search +-{search_half_width} refined to {refined}"


def test_refine_frequency_keeps_selection_when_refinement_fails(qt_app, monkeypatch):
    measurement = md_measurement({"BW": sine(50000, 5.0, 1.0, 100.0)})
    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = 5000
    controller.auto_detect_peaks = False
    controller.plot()

    window = spectrum.AnalysisWindow(controller, "MD")
    controller.selected_freqs = [5.0]
    monkeypatch.setattr(spectrum, "hs_units", lambda *a, **k: None)

    window.refineFrequency()  # must not raise ZeroDivisionError

    assert controller.selected_freqs[-1] == pytest.approx(5.0)


def test_refinement_range_is_bounded_by_the_selected_frequency():
    """A wide visible axis must not let a low-frequency peak be dragged to DC."""
    halfwidth, f_min, f_max = frequency_refinement_range(0.03, 0.0, 39.0)
    # 1% of the 39 1/m axis would be 0.39; the relative cap keeps it at 10%.
    assert halfwidth == pytest.approx(0.003)
    assert f_min > 0 and f_min == pytest.approx(0.027)
    assert f_max == pytest.approx(0.033)

    # A high-frequency selection is still limited by the view fraction.
    halfwidth, f_min, f_max = frequency_refinement_range(20.0, 0.0, 39.0)
    assert halfwidth == pytest.approx(0.39)

    assert frequency_refinement_range(0.0, 0.0, 39.0) == (None, None, None)
    assert frequency_refinement_range(None, 0.0, 39.0) == (None, None, None)


def test_refine_frequency_stays_near_the_selected_peak(qt_app):
    """Regression for the reported ZeroDivisionError: refinement used to walk
    down to the lowest FFT bin, and eventually to zero."""
    measurement = md_measurement({"BW": sine(200000, 0.05, 1.0, 100.0)})
    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = 20000
    controller.auto_detect_peaks = False
    controller.plot()

    window = spectrum.AnalysisWindow(controller, "MD")
    controller.selected_freqs = [0.05]
    window.refineFrequency()

    refined = controller.selected_freqs[-1]
    assert refined > 0
    assert refined == pytest.approx(0.05, rel=0.1)


def test_frequency_snapping_never_returns_dc(qt_app):
    measurement = md_measurement({"BW": sine(50000, 5.0, 1.0, 100.0)})
    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = 5000
    controller.auto_detect_peaks = False
    controller.plot()

    assert controller.frequencies[0] == 0.0  # the DC bin is in range
    assert controller.snap_frequency_to_bin(0.0) is None


# --------------------------------------------------------------------------
# Formation index
# --------------------------------------------------------------------------

def naive_formation_index(values, window_size):
    """Deliberately literal reference: f_N = std / sqrt(mean) per window."""
    return np.array([
        np.std(values[i:i + window_size]) / np.sqrt(np.mean(values[i:i + window_size]))
        for i in range(len(values) - window_size + 1)
    ])


def test_formation_index_matches_naive_reference():
    values = np.random.default_rng(5).normal(80.0, 1.5, 5000)
    controller = formation.AnalysisController.__new__(formation.AnalysisController)
    fast = formation.AnalysisController.calculate_formation_index(controller, values, 400)
    assert np.allclose(fast, naive_formation_index(values, 400), atol=1e-9)


def test_formation_index_scales_linearly_with_standard_deviation():
    """f_N is sigma/sqrt(b): doubling the variation must double the index, not
    quadruple it as a variance-based formula would."""
    controller = formation.AnalysisController.__new__(formation.AnalysisController)
    means = []
    for standard_deviation in (1.0, 2.0):
        values = np.random.default_rng(6).normal(80.0, standard_deviation, 20000)
        means.append(np.mean(
            formation.AnalysisController.calculate_formation_index(controller, values, 400)))
    assert means[1] / means[0] == pytest.approx(2.0, abs=0.05)
    assert means[0] == pytest.approx(1.0 / np.sqrt(80.0), rel=0.03)


def test_formation_index_handles_short_and_constant_input():
    controller = formation.AnalysisController.__new__(formation.AnalysisController)
    calculate = formation.AnalysisController.calculate_formation_index
    assert len(calculate(controller, np.ones(10), 400)) == 0
    constant = calculate(controller, np.full(1000, 80.0), 400)
    assert len(constant) == 601 and np.allclose(constant, 0.0)


# --------------------------------------------------------------------------
# Calculated channels
# --------------------------------------------------------------------------

def test_density_and_bulk_units_and_values():
    """Density in g/cm^3 is BW[g/m2] / caliper[um]; bulk is its reciprocal."""
    frame = pd.DataFrame({"BW": [80.0, 74.0], "Caliper": [100.0, 129.0]})
    density = settings.calc_density(frame)
    bulk = settings.calc_bulk(frame)

    assert density.iloc[0] == pytest.approx(0.8)
    assert bulk.iloc[0] == pytest.approx(1.25)
    assert np.allclose(density * bulk, 1.0)

    declared = {channel["name"]: channel["unit"] for channel in settings.CALCULATED_CHANNELS}
    assert declared["Density"] == "g/cm^3"
    assert declared["Bulk"] == "cm^3/g"


# --------------------------------------------------------------------------
# Non-finite handling
# --------------------------------------------------------------------------

def test_interpolate_non_finite_fills_gaps_and_edges():
    values = np.array([np.nan, 1.0, np.nan, 3.0, np.inf])
    filled, count = interpolate_non_finite(values)
    assert count == 3
    assert np.isfinite(filled).all()
    assert filled[2] == pytest.approx(2.0)
    assert filled[0] == pytest.approx(1.0) and filled[4] == pytest.approx(3.0)

    untouched = np.array([1.0, 2.0, 3.0])
    filled, count = interpolate_non_finite(untouched)
    assert count == 0 and np.allclose(filled, untouched)


def test_bandpass_filter_survives_non_finite_samples():
    clean = sine(20000, 5.0)
    gapped = clean.copy()
    gapped[[100, 5000, 5001, 19999]] = np.nan

    filtered_clean = bandpass_filter(clean, 0.0, 30.0, FS)
    filtered_gapped = bandpass_filter(gapped, 0.0, 30.0, FS)

    assert np.isfinite(filtered_gapped).all()
    assert filtered_gapped.std() == pytest.approx(filtered_clean.std(), rel=0.01)


def test_bandpass_filter_degenerate_band_returns_mean_level():
    values = sine(5000, 5.0, offset=100.0)
    filtered = bandpass_filter(values, 5.0, 5.0, FS)
    assert np.isfinite(filtered).all()
    assert filtered == pytest.approx(np.full(len(values), values.mean()))


def test_spectrum_survives_a_single_non_finite_sample(qt_app):
    amplitude = 3.0
    frequency = 200 * FS / 5000
    values = sine(100000, frequency, amplitude, 100.0)
    values[500] = np.nan
    measurement = md_measurement({"BW": values})

    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = 5000
    controller.auto_detect_peaks = False
    controller.plot()

    assert np.isfinite(controller.amplitudes).all()
    peak = controller.amplitudes[np.argmin(np.abs(controller.frequencies - frequency))]
    assert peak == pytest.approx(amplitude, rel=0.02)


# --------------------------------------------------------------------------
# Failed plots must not leave stale results behind
# --------------------------------------------------------------------------

def test_failed_plot_clears_results_and_report_stats(qt_app):
    measurement = md_measurement({"BW": sine(20000, 5.0, 1.0, 100.0)})

    class FailingController(time_domain.AnalysisController):
        fail = False

        def plot(self):
            if self.fail:
                raise RuntimeError("forced failure")
            return super().plot()

    controller = FailingController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.band_pass_low, controller.band_pass_high = 0.0, 30.0
    controller.updatePlot()
    assert len(controller.data) > 0
    assert stats_for_report(controller) is not None

    controller.fail = True
    controller.updatePlot()

    assert controller.plot_failed is True
    assert len(controller.data) == 0
    assert stats_for_report(controller) is None

    widget = StatsWidget(show_slope=True)
    widget.update_statistics(controller.data, "g/m2", None)
    assert all(w.value_label.text() == "--" for w in widget.widgets.values())


# --------------------------------------------------------------------------
# SOS harmonic fitting
# --------------------------------------------------------------------------

@pytest.mark.parametrize("frequency", [1.0, 5.0, 10.0, 20.0])
def test_harmonic_fit_returns_signed_full_revolution(frequency):
    amplitude = 3.0
    values = sine(40000, frequency, amplitude, offset=100.0)
    revolution = harmonic_fitting_units(values, FS, frequency)

    assert len(revolution) == settings.SOS_REVOLUTION_POINTS
    assert revolution.mean() == pytest.approx(0.0, abs=1e-6)
    assert revolution.max() == pytest.approx(amplitude, rel=0.01)
    assert revolution.min() == pytest.approx(-amplitude, rel=0.01)

    # A pure fundamental has exactly one maximum per revolution. Taking abs()
    # of the fitted waveform would give two.
    wrapped = np.concatenate(([revolution[-1]], revolution, [revolution[0]]))
    maxima = np.sum((wrapped[1:-1] > wrapped[:-2]) & (wrapped[1:-1] > wrapped[2:]))
    assert maxima == 1


def test_harmonic_fit_recovers_phase():
    """The revolution is on an angular grid, so a known phase lands at a known
    angle regardless of whether Fs/w is an integer."""
    frequency = 10.0  # Fs/w = 7.8125 samples, deliberately not an integer
    distances = np.arange(40000) * SAMPLE_STEP
    values = 100.0 + np.sin(2 * np.pi * frequency * distances)
    revolution = harmonic_fitting_units(values, FS, frequency)

    peak_angle = np.argmax(revolution) / len(revolution) * 360.0
    assert peak_angle == pytest.approx(90.0, abs=2.0)


# --------------------------------------------------------------------------
# Cepstrum
# --------------------------------------------------------------------------

def harmonic_series_measurement(period=2.0, length=200000, noise=0.0, seed=7):
    """A signal whose only periodicity is a harmonic family of the given period."""
    distances = np.arange(length) * SAMPLE_STEP
    harmonics = sum((1.0 / k) * np.sin(2 * np.pi * k * distances / period + k)
                    for k in range(1, 9))
    values = 100.0 + harmonics + \
        np.random.default_rng(seed).normal(0, noise, len(distances))
    return md_measurement({"BW": values})


def cepstrum_controller(measurement, nperseg=20000, **attributes):
    controller = cepstrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.nperseg = nperseg
    for name, value in attributes.items():
        setattr(controller, name, value)
    return controller


@pytest.mark.parametrize("noise", [0.0, 0.2, 1.0])
def test_cepstrum_finds_a_known_period(qt_app, noise):
    """Peak detection must rank the true period first, not the envelope hump."""
    period = 2.0
    measurement = harmonic_series_measurement(period=period, noise=noise)

    controller = cepstrum_controller(measurement, auto_detect_peaks=True)
    controller.plot()

    assert controller.selected_freqs
    assert controller.selected_freqs[0] == pytest.approx(period, abs=2 * SAMPLE_STEP)


def test_cepstrum_responds_to_segment_length(qt_app):
    """The spectrum length control must actually change the cepstrum.

    The bins are one sample step apart whatever the window length, so the axis
    is not the thing that changes here - the amplitudes are, because the Welch
    averaging they come from does.
    """
    distances = np.arange(100000) * SAMPLE_STEP
    values = 100.0 + np.sin(2 * np.pi * distances / 2.0)
    measurement = md_measurement({"BW": values})

    results = []
    for nperseg in (5000, 20000):
        controller = cepstrum_controller(measurement, nperseg=nperseg)
        controller.plot()
        results.append(controller.cepstrum_amplitudes.copy())

    assert len(results[0]) == len(results[1])
    assert not np.allclose(results[0], results[1])


@pytest.mark.parametrize("nperseg", [20000, 20001])
def test_cepstrum_quefrency_step_is_the_sample_step(qt_app, nperseg):
    """Quefrency is a period, so its bins are spaced one sample apart.

    An odd segment length must not skew the scale: irfft reconstructs an even
    number of samples, so the controller has to round the segment down.
    """
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement, nperseg=nperseg)
    controller.plot()

    steps = np.diff(controller.quefrencies)
    assert steps == pytest.approx(SAMPLE_STEP)


def test_cepstrum_quefrency_range_clips_the_result(qt_app):
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement,
                                     quefrency_range_low=1.0,
                                     quefrency_range_high=3.0)
    controller.plot()

    assert len(controller.quefrencies) > 0
    assert controller.quefrencies[0] >= 1.0
    assert controller.quefrencies[-1] <= 3.0
    assert len(controller.cepstrum_amplitudes) == len(controller.quefrencies)


def test_cepstrum_snaps_a_selection_to_a_bin(qt_app):
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement)
    controller.plot()

    off_bin = controller.quefrencies[10] + 0.4 * SAMPLE_STEP
    snapped = controller.snap_quefrency_to_bin(off_bin)

    assert snapped == pytest.approx(controller.quefrencies[10])

    # A zero period has no frequency, so the DC bin must refuse selection when
    # the range is opened up far enough to include it.
    zero_included = cepstrum_controller(measurement, quefrency_range_low=0.0)
    zero_included.plot()
    assert zero_included.quefrencies[0] == 0.0
    assert zero_included.snap_quefrency_to_bin(0.0) is None


def test_cepstrum_refinement_beats_the_bin_spacing(qt_app):
    """A period between two bins should refine closer than the bins allow."""
    period = 2.0 + 0.5 * SAMPLE_STEP
    measurement = harmonic_series_measurement(period=period)

    controller = cepstrum_controller(measurement, auto_detect_peaks=True)
    controller.plot()

    selected = controller.selected_freqs[-1]
    refined = controller.refine_selected_quefrency()

    assert refined is not None
    assert abs(refined - period) < abs(selected - period)


def test_cepstrum_reports_the_period_in_every_unit(qt_app):
    """The harmonic series base has to be readable as m, cm, 1/m and Hz."""
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement, machine_speed=600.0)
    controller.plot()

    quefrency = 2.0
    assert controller.quefrency_to_frequency(quefrency) == pytest.approx(0.5)
    # 0.5 1/m at 600 m/min = 10 m/s is 5 Hz.
    assert controller.quefrency_to_hz(quefrency) == pytest.approx(5.0)
    assert controller.quefrency_to_frequency(0.0) is None
    assert controller.quefrency_to_hz(0.0) is None

    description = controller.describe_quefrency(quefrency, amplitude=1.0)
    assert "2.0000 m" in description
    assert "200.00 cm" in description
    assert "0.500 1/m" in description
    assert "5.00 Hz" in description


def test_cepstrum_stats_table_lists_the_selection(qt_app):
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement, machine_speed=600.0,
                                     auto_detect_peaks=True)
    controller.plot()

    stats = controller.getStatsTableData()

    assert stats[0] == ["Quefrency [m]", "Wavelength [cm]",
                        "Frequency [1/m]", "Frequency [Hz]", "Amplitude"]
    assert len(stats) == 2
    assert float(stats[1][0]) == pytest.approx(2.0, abs=2 * SAMPLE_STEP)


def test_cepstrum_manual_selection_survives_redraws(qt_app):
    """Peak detection runs on every recompute and must not overwrite a choice.

    Selecting, scrolling or refining while "Detect peaks" is ticked used to be
    undone by the redraw that the same action triggered.
    """
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement, auto_detect_peaks=True)
    window = cepstrum.AnalysisWindow(controller, "MD")

    detected = controller.selected_freqs[-1]
    elsewhere = detected * 1.5

    assert window.select_quefrency_at(controller.ax, elsewhere)
    assert not controller.auto_detect_peaks
    picked = controller.selected_freqs[-1]
    assert picked == pytest.approx(elsewhere, abs=SAMPLE_STEP)

    window.refresh()
    assert controller.selected_freqs[-1] == picked

    # A refinement lands between bins, so the redraw must not snap it back.
    controller.selected_freqs = [detected]
    window.refineFrequency()
    refined = controller.selected_freqs[-1]
    window.refresh()
    assert controller.selected_freqs[-1] == refined

    window.clearFrequency()
    assert controller.selected_freqs == []
    assert window.selectedQuefrencyLabel.text() == "Selected quefrency: None"


def test_cepstrum_export_carries_the_unit_columns(qt_app):
    measurement = harmonic_series_measurement()

    controller = cepstrum_controller(measurement)
    controller.plot()

    exported = controller.getExportData()

    assert list(exported.columns) == ["Quefrency [m]", "Wavelength [cm]",
                                      "Frequency [1/m]", "BW cepstrum amplitude"]
    assert exported["Wavelength [cm]"].iloc[0] == pytest.approx(
        100 * exported["Quefrency [m]"].iloc[0])
    assert exported["Frequency [1/m]"].iloc[0] == pytest.approx(
        1 / exported["Quefrency [m]"].iloc[0])


# --------------------------------------------------------------------------
# CD strip alignment
# --------------------------------------------------------------------------

def unequal_strip_measurement():
    """Three CD strips of deliberately different lengths.

    The channel is a ramp equal to its own sample index, so the first and last
    value of a trimmed strip state exactly which samples were kept.
    """
    sample_step = 0.001
    length = 3000
    distances = np.arange(length) * sample_step
    peak_locations = [0.0, 1.0, 2.05, 2.95]

    measurement = Measurement(
        channel_df=pd.DataFrame({"BW": np.arange(length, dtype=float)}),
        channels=["BW"],
        units={"BW": "g/m2"},
        distances=distances,
        sample_step=sample_step,
        peak_locations=peak_locations,
        tape_width_mm=0.0,
    )
    return measurement, distances, peak_locations


def test_cd_segments_align_left_by_default(monkeypatch):
    """Every profile begins at its leading tape."""
    monkeypatch.setattr(settings, "CD_SEGMENT_ALIGNMENT", "left")
    measurement, distances, peak_locations = unequal_strip_measurement()
    measurement.split_data_to_segments()
    segments = measurement.segments["BW"]

    assert segments.shape[0] == 3
    for index, strip in enumerate(segments):
        start = np.searchsorted(distances, peak_locations[index], side='left')
        assert strip[0] == pytest.approx(float(start))


def test_cd_segments_align_right(monkeypatch):
    """Every profile ends at its trailing tape."""
    monkeypatch.setattr(settings, "CD_SEGMENT_ALIGNMENT", "right")
    measurement, distances, peak_locations = unequal_strip_measurement()
    measurement.split_data_to_segments()
    segments = measurement.segments["BW"]

    for index, strip in enumerate(segments):
        end = np.searchsorted(distances, peak_locations[index + 1], side='right')
        assert strip[-1] == pytest.approx(float(end - 1))


def test_cd_segments_align_center(monkeypatch):
    """Equal amounts are cut from both ends of each strip."""
    monkeypatch.setattr(settings, "CD_SEGMENT_ALIGNMENT", "center")
    measurement, distances, peak_locations = unequal_strip_measurement()
    measurement.split_data_to_segments()
    segments = measurement.segments["BW"]

    common_length = segments.shape[1]
    for index, strip in enumerate(segments):
        start = np.searchsorted(distances, peak_locations[index], side='left')
        end = np.searchsorted(distances, peak_locations[index + 1], side='right')
        offset = (end - start - common_length) // 2
        assert strip[0] == pytest.approx(float(start + offset))


def test_cd_segment_alignment_falls_back_to_left(monkeypatch):
    monkeypatch.setattr(settings, "CD_SEGMENT_ALIGNMENT", "sideways")
    measurement, distances, peak_locations = unequal_strip_measurement()
    measurement.split_data_to_segments()
    segments = measurement.segments["BW"]

    for index, strip in enumerate(segments):
        start = np.searchsorted(distances, peak_locations[index], side='left')
        assert strip[0] == pytest.approx(float(start))


# --------------------------------------------------------------------------
# Correlation matrix
# --------------------------------------------------------------------------

def correlated_measurement(length=20000, channel_count=4):
    rng = np.random.default_rng(11)
    base = rng.normal(size=length)
    channels = {}
    for index in range(channel_count):
        channels[f"C{index}"] = (100.0 + index + (1.0 - 0.2 * index) * base
                                 + rng.normal(0, 0.5, length))
    return md_measurement(channels)


def build_correlation_controller(qt_app, measurement=None):
    measurement = measurement or correlated_measurement()
    controller = correlation_matrix.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.band_pass_low, controller.band_pass_high = 0.0, 30.0
    controller.plot()
    return controller


def test_correlation_matrix_draws_only_the_lower_triangle(qt_app):
    controller = build_correlation_controller(qt_app)
    count = len(controller.panel_channels)

    created = [(row, column)
               for row in range(count) for column in range(count)
               if controller.axes[row, column] is not None]

    assert all(column <= row for row, column in created)
    assert len(created) == count * (count + 1) // 2
    assert len(controller.figure.axes) == count * (count + 1) // 2


def test_correlation_matrix_annotations_use_the_full_slice(qt_app):
    controller = build_correlation_controller(qt_app)
    correlations = controller.data_slice.corr()

    for (row, column), annotation in controller.correlation_labels.items():
        assert float(annotation.get_text()) == pytest.approx(
            correlations.iloc[row, column], abs=0.005)


def test_correlation_matrix_reuses_panels_across_refreshes(qt_app):
    controller = build_correlation_controller(qt_app)
    before = [id(ax) for ax in controller.figure.axes]

    controller.band_pass_high = 20.0
    controller.plot()

    assert [id(ax) for ax in controller.figure.axes] == before

    # A different channel set must rebuild rather than reuse.
    controller.measurement = correlated_measurement(channel_count=3)
    controller.plot()
    assert len(controller.panel_channels) == 3
    assert len(controller.figure.axes) == 3 * 4 // 2


def test_correlation_matrix_updates_values_when_reusing(qt_app):
    controller = build_correlation_controller(qt_app)
    first = {key: line.get_xydata().copy()
             for key, line in controller.scatter_lines.items()}

    controller.analysis_range_high = controller.measurement.distances[-1] / 2
    controller.plot()

    changed = any(not np.array_equal(first[key], line.get_xydata())
                  for key, line in controller.scatter_lines.items())
    assert changed, "reused panels kept the previous data"


# --------------------------------------------------------------------------
# Batched band pass filtering
# --------------------------------------------------------------------------

def test_bandpass_filter_columns_matches_per_column_filtering():
    rng = np.random.default_rng(12)
    length, channel_count = 30000, 5
    data = np.column_stack([
        100 + index + sine(length, 2.0 * (index + 1)) + rng.normal(0, 0.3, length)
        for index in range(channel_count)])
    data[700, 1] = np.nan  # exercise the gap-filling path

    per_column = np.column_stack([
        bandpass_filter(data[:, index], 0.0, 30.0, FS)
        for index in range(channel_count)])
    batched = bandpass_filter_columns(data, 0.0, 30.0, FS)

    assert np.allclose(per_column, batched, atol=1e-9)
    assert np.allclose(batched.mean(axis=0), np.nanmean(data, axis=0), atol=1e-9)


def test_bandpass_filter_columns_handles_degenerate_band():
    data = np.column_stack([sine(5000, 5.0, offset=100.0),
                            sine(5000, 7.0, offset=50.0)])
    filtered = bandpass_filter_columns(data, 5.0, 5.0, FS)
    assert np.allclose(filtered, data.mean(axis=0))


# --------------------------------------------------------------------------
# Channels with no usable data
# --------------------------------------------------------------------------

def test_all_nan_channels_are_dropped(monkeypatch):
    monkeypatch.setattr(settings, "DROP_CHANNEL_NAN_FRACTION", 1.0)
    frame = pd.DataFrame({
        "Good": np.arange(100, dtype=float),
        "Dead": np.full(100, np.nan),
        "Partly": np.where(np.arange(100) < 50, np.nan, 1.0),
    })
    units = {"Good": "g/m2", "Dead": "g/m2", "Partly": "g/m2"}

    kept, kept_units = drop_unusable_channels(frame.copy(), dict(units))

    assert list(kept.columns) == ["Good", "Partly"]
    assert "Dead" not in kept_units


def test_nan_channel_threshold_is_configurable(monkeypatch):
    frame = pd.DataFrame({
        "Good": np.arange(100, dtype=float),
        "Partly": np.where(np.arange(100) < 50, np.nan, 1.0),
    })

    monkeypatch.setattr(settings, "DROP_CHANNEL_NAN_FRACTION", 0.4)
    kept, _ = drop_unusable_channels(frame.copy(), {})
    assert list(kept.columns) == ["Good"]

    monkeypatch.setattr(settings, "DROP_CHANNEL_NAN_FRACTION", None)
    kept, _ = drop_unusable_channels(frame.copy(), {})
    assert list(kept.columns) == ["Good", "Partly"]


# --------------------------------------------------------------------------
# Frequency selection from the plot
# --------------------------------------------------------------------------

class _FakeMouseEvent:
    """Matplotlib mouse event stand-in. guiEvent is None so a popup falls back
    to the cursor position rather than needing a real Qt event."""

    def __init__(self, inaxes, button, xdata=None, ydata=None):
        self.inaxes = inaxes
        self.button = button
        self.xdata = xdata
        self.ydata = ydata
        self.guiEvent = None


def _spectrum_window(qt_app):
    measurement = md_measurement({"BW": sine(100000, 5.0, 1.0, 100.0)})
    controller = spectrum.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.nperseg = 20000
    controller.auto_detect_peaks = False
    controller.plot()
    window = spectrum.AnalysisWindow(controller, "MD")
    controller.selected_freqs = []
    return controller, window


def test_spectrum_right_click_offers_select_frequency(qt_app):
    """The selection entry rides on the canvas menu, not a second menu.

    An analysis that pops its own menu from a button_press_event handler shows
    it on top of the annotation menu the canvas raises for the same click.
    """
    from matplotlib.backend_bases import MouseButton

    controller, window = _spectrum_window(qt_app)

    assert controller.canvas.context_menu_actions_provider == window.contextMenuActions

    event = _FakeMouseEvent(controller.ax, MouseButton.RIGHT, xdata=7.5)
    (label, callback, enabled), = window.contextMenuActions(event)
    assert label == "Select frequency"
    assert enabled

    callback(event)
    assert controller.selected_freqs[-1] == pytest.approx(7.5, abs=0.5)

    # Without a position on the axis the entry is offered but disabled.
    (_, _, enabled), = window.contextMenuActions(
        _FakeMouseEvent(None, MouseButton.RIGHT))
    assert not enabled


def test_spectrum_menu_action_matches_selector_button(qt_app):
    from matplotlib.backend_bases import MouseButton

    controller, window = _spectrum_window(qt_app)

    # What the menu entry calls.
    assert window.select_frequency_at(controller.ax, 5.0) is True
    from_menu = controller.selected_freqs[-1]

    # What the configured selector button does.
    controller.selected_freqs = []
    window.onclick(_FakeMouseEvent(controller.ax, MouseButton.MIDDLE, xdata=5.0))
    from_button = controller.selected_freqs[-1]

    assert from_menu == pytest.approx(from_button)

    # A left click must not select anything.
    before = len(controller.selected_freqs)
    window.onclick(_FakeMouseEvent(controller.ax, MouseButton.LEFT, xdata=12.0))
    assert len(controller.selected_freqs) == before


def test_spectrogram_menu_selects_on_the_frequency_axis(qt_app):
    from matplotlib.backend_bases import MouseButton

    measurement = md_measurement({"BW": sine(100000, 5.0, 1.0, 100.0)})
    controller = spectrogram.AnalysisController(measurement, "MD")
    controller.analysis_range_low = 0.0
    controller.analysis_range_high = measurement.distances[-1]
    controller.frequency_range_low = 0.0
    controller.frequency_range_high = FS / 2
    controller.plot()
    window = spectrogram.AnalysisWindow(controller, "MD")
    controller.selected_freqs = []

    # The spectrogram puts frequency on the y axis.
    assert window.select_frequency_at(controller.ax, 5.0) is True
    assert controller.selected_freqs[-1] == pytest.approx(5.0, abs=0.5)

    # The canvas menu entry drives the same y-axis selection.
    assert controller.canvas.context_menu_actions_provider == window.contextMenuActions
    controller.selected_freqs = []
    event = _FakeMouseEvent(controller.ax, MouseButton.RIGHT, ydata=8.25)
    (label, callback, enabled), = window.contextMenuActions(event)
    assert label == "Select frequency"
    assert enabled
    callback(event)
    assert controller.selected_freqs[-1] == pytest.approx(8.25, abs=0.5)
