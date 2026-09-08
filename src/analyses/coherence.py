import logging

from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import (hs_units, safe_spectral_params, segment_count,
                                     effective_segment_count, coherence_significance_level,
                                     max_nperseg_for_effective_segments,
                                     frequency_refinement_range,
                                     interpolate_non_finite)
from utils.plot_formatting import wavelength_labels_cm_from_frequencies
from utils import store
from gui.components import (
    AnalysisRangeMixin,
    DoubleChannelMixin,
    FrequencyRangeMixin,
    MachineSpeedMixin,
    SampleSelectMixin,
    SpectrumLengthMixin,
    ShowWavelengthMixin,
    ShowFrequencyInHzMixin,
    CopyPlotMixin,
    FrequencyMarksControlsMixin,
    ChildWindowCloseMixin,
    ExportMixin,
    ControlsPanelWidget
)
from gui.paper_machine_data import PaperMachineDataWindow
import matplotlib.patches as mpatches
from matplotlib.ticker import AutoMinorLocator
from scipy.signal import coherence
import settings
from utils.frequency_marks import FrequencyMarksMixin
import numpy as np
import pandas as pd

analysis_name = "Coherence"
analysis_types = ["MD", "CD"]


def normalize_for_coherence(data):
    """Z-score the input. Coherence is scale invariant, so this only keeps the
    cross- and auto-spectra in a comparable numeric range."""
    data = np.asarray(data, dtype=float).reshape(-1)
    if len(data) < 2:
        return None

    data, _ = interpolate_non_finite(data, context="coherence input")

    std = np.std(data)
    if not np.isfinite(std) or std == 0:
        return None

    return (data - np.mean(data)) / std


def tabular_legend(ax, col_labels, data, *args, **kwargs):
    """
    Custom legend function
    Parameters:
    - ax : matplotlib.axes.Axes
    - col_labels : list of column labels
    - data : list of lists containing the values for each legend entry
    """
    # Get current legend handles
    handles, _ = ax.get_legend_handles_labels()

    # Create a blank patch for column labels (no handle)
    blank_patch = mpatches.Rectangle(
        (0, 0), 1, 1, fc="w", edgecolor="none", linewidth=0
    )

    all_rows = [col_labels] + data  # Ensure headers are considered

    # Determine column widths based on the widest element per column
    col_widths = [max(len(str(item)) for item in col)
                  for col in zip(*all_rows)]

    # Format each row with proper spacing
    formatted_rows = [
        "  ".join(str(item).rjust(width)
                  for item, width in zip(row, col_widths))
        for row in all_rows  # Include column labels here
    ]

    # for i in formatted_rows:
    #     print(i)

    # Construct table headers
    # Add blank patch for header alignment
    table_handles = [blank_patch] + handles

    # Create the legend
    legend = ax.legend(
        table_handles,
        formatted_rows,
        prop={'family': 'monospace'},
        loc=kwargs.pop("loc", "upper right"),
        handletextpad=kwargs.pop("handletextpad", 0),
        **kwargs
    )

    return legend


class AnalysisController(AnalysisControllerBase, FrequencyMarksMixin, ExportMixin):
    #: Magnitude-squared coherence is dimensionless, and written with a C.
    amplitude_symbol = "C"
    channel: str
    channel2: str
    nperseg: float
    overlap: float
    frequency_range_low: float
    frequency_range_high: float
    peak_detection_range_min: float
    peak_detection_range_max: float
    spectrum_length_slider_min: float
    spectrum_length_slider_max: float
    analysis_range_low: float
    analysis_range_high: float
    machine_speed: float
    selected_elements: list[str]
    selected_samples: list[int]
    selected_freqs: list[float]
    show_wavelength: bool
    show_frequency_in_hz: bool
    auto_detect_peaks: bool

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.ax = None

        # Dynamic initialization based on window type
        spectrum_defaults = {
            "MD": {
                "nperseg": settings.MD_COHERENCE_DEFAULT_LENGTH,
                "range_min": settings.MD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.MD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "peak_detection_range_min": settings.MD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.MD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.MD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.MD_COHERENCE_OVERLAP,
                "spectrum_length_slider_min": settings.MD_COHERENCE_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.MD_COHERENCE_LENGTH_SLIDER_MAX
            },
            "CD": {
                "nperseg": settings.CD_COHERENCE_DEFAULT_LENGTH,
                "range_min": settings.CD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.CD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "peak_detection_range_min": settings.CD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.CD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.CD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.CD_COHERENCE_OVERLAP,
                "spectrum_length_slider_min": settings.CD_COHERENCE_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.CD_COHERENCE_LENGTH_SLIDER_MAX
            }
        }
        config = spectrum_defaults[self.window_type]
        self.channels = self.measurement.channels
        self.spectral_window = settings.SPECTRUM_WELCH_WINDOW

        self.set_default('channel', self.channels[0])
        self.set_default('channel2', self.channels[0])
        self.set_default('nperseg', config["nperseg"])
        self.set_default('overlap', config["overlap"])
        self.set_default('frequency_range_low', self.max_freq * config["range_min"])
        self.set_default('frequency_range_high', self.max_freq * config["range_max"])
        self.set_default('peak_detection_range_min', config["peak_detection_range_min"])
        self.set_default('peak_detection_range_max', config["peak_detection_range_max"])
        self.set_default('spectrum_length_slider_min', config["spectrum_length_slider_min"])
        self.set_default('spectrum_length_slider_max', config["spectrum_length_slider_max"])
        self.set_default('analysis_range_low', config["analysis_range_low"] * self.max_dist)
        self.set_default('analysis_range_high', config["analysis_range_high"] * self.max_dist)
        self.set_default('machine_speed', settings.PAPER_MACHINE_SPEED_DEFAULT)
        self.set_default('selected_samples', self.measurement.selected_samples.copy())
        self.set_default('show_wavelength', settings.SHOW_WAVELENGTH_DEFAULT)
        self.set_mark_defaults()

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax
        self.frequencies = np.array([])
        self.amplitudes = np.array([])
        self.reset_marks()
        self.n_segments = 0
        self.effective_segments = 0.0
        self.significance_level = None
        ax.figure.set_constrained_layout(True)
        ax.set_xlabel("Frequency [1/m]")
        ax.set_ylabel("Magnitude-squared coherence")

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.measurement.measurement_label} Coherence ({
                self.channel} vs {self.channel2})")

        if settings.SPECTRUM_MINOR_GRID:
            ax.grid(True, which='both')
            ax.minorticks_on()
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(4))
            ax.grid(True, which='minor', linestyle=':', linewidth=0.5)
        else:
            ax.grid()

        if self.window_type == "MD":
            self.low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')
            data1 = self.measurement.channel_df[self.channel][self.low_index:self.high_index]
            data2 = self.measurement.channel_df[self.channel2][self.low_index:self.high_index]

            self.limit_segment_length(min(len(data1), len(data2)))
            spectral_params = safe_spectral_params(
                self.nperseg,
                self.overlap,
                min(len(data1), len(data2)),
                require_segment_shorter_than_data=True,
            )
            data1_norm = normalize_for_coherence(data1)
            data2_norm = normalize_for_coherence(data2)
            if spectral_params is None or data1_norm is None or data2_norm is None:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas
            nperseg, noverlap = spectral_params

            self.n_segments = segment_count(
                min(len(data1), len(data2)), nperseg, noverlap)
            if not self.has_enough_segments(ax):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            # Calculate coherence
            f, Cxy = coherence(
                data1_norm,
                data2_norm,
                fs=self.fs,
                window=self.spectral_window,
                nperseg=nperseg,
                noverlap=noverlap
            )
            # ax.plot(f, Cxy)

        elif self.window_type == "CD":

            self.low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            if len(self.selected_samples) == 0:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            x = self.measurement.cd_distances[self.low_index:self.high_index]
            sample_pairs = [
                (
                    self.measurement.segments[self.channel][sample_idx][self.low_index:self.high_index],
                    self.measurement.segments[self.channel2][sample_idx][self.low_index:self.high_index],
                )
                for sample_idx in self.selected_samples
                if (
                    0 <= sample_idx < len(self.measurement.segments[self.channel])
                    and 0 <= sample_idx < len(self.measurement.segments[self.channel2])
                )
            ]
            if not sample_pairs:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            self.limit_segment_length(
                min(len(sample_pairs[0][0]), len(sample_pairs[0][1])))
            spectral_params = safe_spectral_params(
                self.nperseg,
                self.overlap,
                min(len(sample_pairs[0][0]), len(sample_pairs[0][1])),
                require_segment_shorter_than_data=True,
            )
            if spectral_params is None:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas
            nperseg, noverlap = spectral_params

            self.n_segments = segment_count(
                min(len(sample_pairs[0][0]), len(sample_pairs[0][1])), nperseg, noverlap)
            if not self.has_enough_segments(ax):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            spectra = []
            for data1, data2 in sample_pairs:
                data1_norm = normalize_for_coherence(data1)
                data2_norm = normalize_for_coherence(data2)
                if data1_norm is None or data2_norm is None:
                    continue
                f, sample_cxy = coherence(
                    data1_norm,
                    data2_norm,
                    fs=self.fs,
                    window=self.spectral_window,
                    nperseg=nperseg,
                    noverlap=noverlap
                )
                spectra.append(sample_cxy)

            if not spectra:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            Cxy = np.mean(spectra, axis=0)
            # ax.plot(f, Cxy)

        f_low_index = np.searchsorted(f, self.frequency_range_low)
        f_high_index = np.searchsorted(
            f, self.frequency_range_high, side='right')

        amplitude_spectrum = Cxy

        if self.ax:
            xlim = self.ax.get_xlim()
        else:
            xlim = None

        # Plot the amplitude spectrum

        self.frequencies = f[f_low_index:f_high_index]
        self.amplitudes = amplitude_spectrum[f_low_index:f_high_index]

        # Magnitude-squared coherence is biased upward: for uncorrelated inputs
        # its expectation is about 1/(effective segments), not 0. Overlapping
        # segments are correlated, so the effective count is what sets that
        # floor, not the nominal one. The default segment settings keep the
        # floor low enough to read the plot directly, so the threshold is
        # computed for export and logging but not drawn.
        self.effective_segments = effective_segment_count(
            self.spectral_window, nperseg, noverlap, self.n_segments)
        self.significance_level = coherence_significance_level(self.effective_segments)
        if settings.COHERENCE_SHOW_SIGNIFICANCE_LINE and self.significance_level is not None:
            ax.axhline(self.significance_level, color='tab:red',
                       linestyle=':', linewidth=1.2)
        ax.set_ylim(0, 1)

        ax.plot(self.frequencies, self.amplitudes)

        ax.set_ylim(0, 1.1)

        secax = ax.twiny()

        # The Hz axis is only drawn where the Hz reading is shown at all: with
        # no machine speed to convert by it would read zero at every tick.
        if self.show_wavelength or not self.hz_readings_shown():

            def update_secax(*args):
                primary_ticks = ax.get_xticks()
                secax.set_xticks(primary_ticks)
                secax.set_xlim(*ax.get_xlim())
                secax.set_xticklabels(
                    wavelength_labels_cm_from_frequencies(secax.get_xticks()))

            secax.set_xlabel(f"Wavelength [cm]")

        else:

            def update_secax(*args):
                primary_ticks = ax.get_xticks()
                secax.set_xticks(primary_ticks)
                secax.set_xlim(*ax.get_xlim())
                secondary_ticks = secax.get_xticks() * self.machine_speed / 60
                secax.set_xticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])

            secax.set_xlabel(f"Frequency [Hz] at machine speed {
                             self.machine_speed:.1f} m/min")

        ax.set_zorder(secax.get_zorder() + 1)
        update_secax()  # Initial call to update secondary axis

        # Update secondary axis on primary axis changes
        ax.callbacks.connect('xlim_changed', update_secax)
        ax.figure.canvas.mpl_connect('resize_event', update_secax)

        if self.auto_detect_peaks:
            self.detectPeaks()

        self.drawSelectedFrequencies(ax)
        self.drawPaperMachineElements(ax)

        handles, labels = ax.get_legend_handles_labels()

        if settings.SPECTRUM_SHOW_LEGEND:
            if labels:  # This list will be non-empty if there are items to include in the legend
                if settings.SPECTRUM_LEGEND_OUTSIDE_PLOT:
                    leg = tabular_legend(ax, self.legend_columns(), self.legend_data, loc="upper left", bbox_to_anchor=(
                        1.05, 1), borderaxespad=0.)

                    leg.get_frame().set_alpha(0)
                else:
                    ax.legend(handles, labels, loc="upper right")

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def limit_segment_length(self, data_length):
        """Cap the window-length control to what the available data can support.

        Coherence needs many averaged segments; a long segment on a short record
        leaves too few, and at one segment the estimate is identically 1. Rather
        than letting the user select such a setting and then refusing to plot,
        the slider maximum is reduced to the longest segment that still yields
        COHERENCE_TARGET_EFFECTIVE_SEGMENTS independent segments.
        """
        allowed = max_nperseg_for_effective_segments(
            data_length,
            self.overlap,
            settings.COHERENCE_TARGET_EFFECTIVE_SEGMENTS,
            window=self.spectral_window,
        )

        self.spectrum_length_slider_max = min(
            self.spectrum_length_slider_max, allowed)
        self.spectrum_length_slider_min = min(
            self.spectrum_length_slider_min, self.spectrum_length_slider_max)

        if self.nperseg > self.spectrum_length_slider_max:
            logging.info(
                "Reducing coherence window length from %d to %d samples so that "
                "%d independent segments fit in the selected range.",
                int(self.nperseg), int(self.spectrum_length_slider_max),
                settings.COHERENCE_TARGET_EFFECTIVE_SEGMENTS)
            self.nperseg = self.spectrum_length_slider_max

    def has_enough_segments(self, ax):
        """Coherence is only meaningful when several Welch segments are averaged.

        With a single segment the magnitude-squared coherence is identically 1 at
        every frequency regardless of the data, which reads as perfect coherence.
        """
        minimum = getattr(settings, "COHERENCE_MIN_SEGMENTS", 8)
        if self.n_segments >= minimum:
            return True

        message = (
            "Not enough data for a coherence estimate\n"
            f"{self.n_segments} segment(s) of {int(round(self.nperseg))} samples, "
            f"{minimum} required.\n"
            "Reduce the spectrum length or widen the analysis range.")
        ax.text(0.5, 0.5, message, ha='center', va='center',
                transform=ax.transAxes, color='tab:red')
        logging.warning(
            "Coherence needs at least %d segments, got %d; not plotting.",
            minimum, self.n_segments)
        return False

    def amplitude_unit(self):
        return ""

    def mark_amplitude_at(self, freq):
        if freq is None or len(self.frequencies) == 0:
            return None
        if freq < self.frequencies[0] or freq > self.frequencies[-1]:
            return None
        return float(np.interp(freq, self.frequencies, self.amplitudes))

    def standing_peaks(self, view=None):
        """Coherence peaks below the significance level are the estimator's
        own bias, not a shared frequency, and ones below the configured
        minimum share too little variance to act on; neither is selected."""
        peaks = super().standing_peaks(view)
        minimum = settings.COHERENCE_PEAK_DETECTION_MIN
        if self.significance_level is not None:
            minimum = max(minimum, self.significance_level)
        return [(freq, value) for freq, value in peaks if value >= minimum]

    def getStatsTableData(self):
        return None
        stats = []

        # Add headers based on window type
        if self.window_type == "MD":
            stats.append(
                [f"Amplitude {self.measurement.units[self.channel]}", "Wavelength [cm]", "Frequency [Hz]", ])
        elif self.window_type == "CD":
            stats.append(["Amplitude", "Wavelength [m]"])

        # Loop over selected frequencies
        for freq in self.selected_freqs:
            if freq:  # Check if the frequency is valid
                wavelength = 1 / freq  # Calculate wavelength from frequency

                # Find the corresponding amplitude
                amplitude_index = np.argmax(self.frequencies == freq)
                amplitude = self.amplitudes[amplitude_index]

                # Add row based on window type
                if self.window_type == "MD":
                    frequency_in_hz = self.get_freq_in_hz(freq)
                    stats.append([
                        f"{amplitude:.2f}",          # Amplitude
                        f"{100 * wavelength:.2f}",  # Wavelength in meters
                        f"{frequency_in_hz:.2f}"   # Frequency in Hz
                    ])
                elif self.window_type == "CD":
                    stats.append([
                        f"{amplitude:.2f}",          # Amplitude
                        f"{100 * wavelength:.2f}"  # Wavelength in meters
                    ])

        return stats

    def getExportData(self):
        data = {
            "Frequency [1/m]": self.frequencies,
            f"Magnitude-squared coherence {self.channel} vs {self.channel2} [-]": self.amplitudes
        }

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, DoubleChannelMixin, FrequencyRangeMixin, MachineSpeedMixin,
                      SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin,
                      ShowFrequencyInHzMixin, CopyPlotMixin,
                      FrequencyMarksControlsMixin, ChildWindowCloseMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.paperMachineDataWindow = None
        self.sampleSelectorWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self):
        exportAction = self.controller.initExportAction(
            self, "Export spectrum")
        self.file_menu.addAction(exportAction)

        viewMenu = self.menu_bar.addMenu('View')

        self.paperMachineDataAction = QAction('Paper machine data', self)

        if not self.measurement.pm_data:
            self.paperMachineDataAction.setDisabled(True)
        viewMenu.addAction(self.paperMachineDataAction)

        if self.window_type == "CD":
            self.selectSamplesAction = QAction('Select samples', self)
            viewMenu.addAction(self.selectSamplesAction)
            self.selectSamplesAction.triggered.connect(
                self.toggleSelectSamples)

        self.paperMachineDataAction.setCheckable(True)
        self.paperMachineDataAction.triggered.connect(
            self.togglePaperMachineData)

    def togglePaperMachineData(self, checked):
        if self.paperMachineDataWindow is None:
            self.paperMachineDataWindow = PaperMachineDataWindow(
                self.updateElements, self.window_type, self.checked_elements, self.measurement)
            self.paperMachineDataWindow.show()
            selected_freq = self.controller.selected_freqs[-1] if self.controller.selected_freqs else None
            self.paperMachineDataWindow.refresh_pm_data(
                self.controller.machine_speed, selected_freq,
                self.controller.hz_readings_shown())
            self.paperMachineDataWindow.closed.connect(
                self.onPaperMachineDataClosed)
            self.paperMachineDataAction.setChecked(True)
        else:
            self.paperMachineDataWindow.close()

    def updateElements(self, selected_elements=None):
        self.checked_elements = selected_elements
        self.controller.selected_elements = selected_elements
        self.refresh()

    def onPaperMachineDataClosed(self):
        self.paperMachineDataWindow = None
        self.paperMachineDataAction.setChecked(False)

    def initUI(self):
        self.setWindowTitle(f"{analysis_name} ({self.controller.window_type}) - {self.measurement.measurement_label}")
        self.resize(*settings.COHERENCE_WINDOW_SIZE)

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel, 0)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        self.controlsPanel.addWidget(dataSelectionGroup)
        self.addChannelSelectors(dataSelectionLayout) # From DoubleChannelMixin

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addFrequencyRangeSlider(analysisParamsLayout)
        self.addSpectrumLengthSlider(analysisParamsLayout)
        if self.controller.window_type == "MD":
            self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display & Peak Options Group
        displayOptionsGroup = QGroupBox("Display && Peak Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        self.controlsPanel.addWidget(displayOptionsGroup)
        self.addSelectionButtons(displayOptionsLayout)
        if self.controller.window_type == "MD":
            self.addShowWavelengthCheckbox(displayOptionsLayout)
            self.addShowFrequencyInHzCheckbox(displayOptionsLayout)
        self.addFrequencyMarkControls(displayOptionsLayout)

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Add selected frequency label
        self.selectedFrequencyLabel = QLabel("Selected frequency: None")
        plotStatsLayout.addWidget(self.selectedFrequencyLabel)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)
        self.controller.canvas.mpl_connect('button_press_event', self.onclick)
        self.connect_selection_stepping()

        self.refresh()

    def clearFrequency(self):
        self.takeManualControl()
        self.controller.selected_freqs = []
        self.selectedFrequencyLabel.setText("Selected frequency: None")

        self.refresh()

    def refineFrequency(self):
        selected_freqs = self.controller.selected_freqs
        if not selected_freqs:
            print("No selected frequency")
            return
        self.takeManualControl()

        print("Original frequency: ", selected_freqs[-1])
        active_channel_for_data = self.controller.channel
        d = self.measurement.channel_df[active_channel_for_data][self.controller.low_index:self.controller.high_index]
        import time
        start_time = time.time()

        plot_min = self.controller.ax.get_xlim()[0] if self.controller.ax.get_xlim()[0] > 0 else 0
        plot_max = self.controller.ax.get_xlim()[1]
        wrange, search_min, search_max = frequency_refinement_range(
            selected_freqs[-1], plot_min, plot_max)
        if wrange is None:
            logging.warning("Cannot refine a non-positive frequency selection.")
            return

        refined = hs_units(
            d, self.controller.fs, selected_freqs[-1], wrange, search_min, search_max,
            settings.MAX_HARMONICS_FREQUENCY_ESTIMATOR)

        print(self.controller.fs)
        end_time = time.time()
        elapsed_time_ms = (end_time - start_time) * 1000
        print(f"Fundamental frequency estimation took {elapsed_time_ms:.2f} ms")
        print("Refined frequency: ", refined)
        if refined is None or not np.isfinite(refined) or refined <= 0:
            # No usable candidate in the search range: keep the user's selection
            # rather than replacing it with zero, whose wavelength is 1/0.
            logging.warning(
                "Frequency refinement found no candidate in the visible range; keeping %.4f 1/m.",
                selected_freqs[-1])
            return
        self.controller.selected_freqs[-1] = refined
        self.refresh(restore_lim=True)

    def select_frequency_at(self, ax, xdata):
        if ax is None or xdata is None:
            return False
        xlim = ax.get_xlim()
        # Reject zero as well as negative: a wavelength of 1/0 is undefined.
        if not (xlim[0] <= xdata <= xlim[1]) or xdata <= 0:
            return False
        self.record_selection(float(xdata))
        self.refresh(restore_lim=True)
        return True

    def onclick(self, event):
        if event.inaxes is not None and event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:
            self.select_frequency_at(event.inaxes, event.xdata)

    def get_current_view_limits(self):
        if not self.controller.figure.axes:
            return None

        ax = self.controller.figure.axes[0]
        return ax.get_xlim(), ax.get_ylim()

    def restore_view_limits(self, view_limits):
        if view_limits is None or not self.controller.figure.axes:
            return

        ax = self.controller.figure.axes[0]
        x_limits, y_limits = view_limits
        ax.set_xlim(x_limits)
        ax.set_ylim(y_limits)
        self.controller.canvas.draw_idle()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initChannelSelectors(block_signals=True)
        self.initFrequencyRangeSlider(block_signals=True)
        self.initSpectrumLengthSlider(block_signals=True)
        self.initFrequencyMarkControls(block_signals=True)
        if self.window_type == "MD":
            self.initShowWavelengthCheckbox(block_signals=True)
            self.initShowFrequencyInHzCheckbox(block_signals=True)
            self.initMachineSpeedSpinner(block_signals=True)

    def refresh(self, restore_lim=False):
        view_limits = self.get_current_view_limits() if restore_lim else None
        self.controller.updatePlot()
        self.restore_view_limits(view_limits)
        self.refresh_widgets()
        selected_freqs = self.controller.selected_freqs

        machine_speed = self.controller.machine_speed
        if not selected_freqs:
            self.selectedFrequencyLabel.setText("Selected frequency: None")
        elif selected_freqs[-1] and np.isfinite(selected_freqs[-1]):
            wavelength = 1 / selected_freqs[-1]

            if self.window_type == "MD":
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freqs[-1]:.2f} 1/m"
                    f"{self.controller.hz_suffix_for(selected_freqs[-1])}"
                    f" λ = {100*wavelength:.2f} cm"
                )

            elif self.window_type == "CD":
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freqs[-1]:.2f} 1/m (λ = {100*wavelength:.2f} cm)")

        if self.paperMachineDataWindow:
            self.paperMachineDataWindow.refresh_pm_data(
                machine_speed, selected_freqs[-1] if selected_freqs else None,
                self.controller.hz_readings_shown())
