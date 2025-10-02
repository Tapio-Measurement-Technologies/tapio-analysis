from PyQt6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase, Analysis
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import hs_units
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import AutoMinorLocator, LogLocator
from scipy.signal import welch, find_peaks
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    FrequencyRangeMixin,
    MachineSpeedMixin,
    SampleSelectMixin,
    SpectrumLengthMixin,
    ShowWavelengthMixin,
    CopyPlotMixin,
    AutoDetectPeaksMixin,
    ChildWindowCloseMixin,
    ExportMixin,
    ControlsPanelWidget
)
from gui.paper_machine_data import PaperMachineDataWindow
import numpy as np
import pandas as pd
import settings
import matplotlib.patheffects as path_effects
from utils import store
analysis_name = "Spectrum"
analysis_types = ["MD", "CD"]


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


class AnalysisController(AnalysisControllerBase, ExportMixin):
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
    selected_elements: list[dict]
    selected_samples: list[int]
    selected_freqs: list[float]
    show_wavelength: bool
    auto_detect_peaks: bool

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)
        self.ax = None

        # Dynamic initialization based on window type
        spectrum_defaults = {
            "MD": {
                "nperseg": settings.MD_SPECTRUM_DEFAULT_LENGTH,
                "range_min": settings.MD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.MD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "peak_detection_range_min": settings.MD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.MD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.MD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.MD_SPECTRUM_OVERLAP,
                "spectrum_length_slider_min": settings.MD_SPECTRUM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.MD_SPECTRUM_LENGTH_SLIDER_MAX
            },
            "CD": {
                "nperseg": settings.CD_SPECTRUM_DEFAULT_LENGTH,
                "range_min": settings.CD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.CD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "peak_detection_range_min": settings.CD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.CD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.CD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.CD_SPECTRUM_OVERLAP,
                "spectrum_length_slider_min": settings.CD_SPECTRUM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.CD_SPECTRUM_LENGTH_SLIDER_MAX
            }
        }
        config = spectrum_defaults[self.window_type]
        self.data = None
        self.current_vlines = []
        self.spectral_window = settings.SPECTRUM_WELCH_WINDOW

        self.set_default('nperseg', config["nperseg"])
        self.set_default('overlap', config["overlap"])
        self.set_default('frequency_range_low',
                         self.max_freq * config["range_min"])
        self.set_default('frequency_range_high',
                         self.max_freq * config["range_max"])
        self.set_default('peak_detection_range_min',
                         config["peak_detection_range_min"])
        self.set_default('peak_detection_range_max',
                         config["peak_detection_range_max"])
        self.set_default('spectrum_length_slider_min',
                         config["spectrum_length_slider_min"])
        self.set_default('spectrum_length_slider_max',
                         config["spectrum_length_slider_max"])
        self.set_default('analysis_range_low',
                         config["analysis_range_low"] * self.max_dist)
        self.set_default('analysis_range_high',
                         config["analysis_range_high"] * self.max_dist)
        self.set_default('machine_speed', settings.PAPER_MACHINE_SPEED_DEFAULT)
        self.set_default('selected_elements', [])
        self.set_default('selected_samples',
                         self.measurement.selected_samples.copy())
        self.set_default('selected_freqs', [])
        self.set_default('show_wavelength', settings.SHOW_WAVELENGTH_DEFAULT)
        self.set_default('auto_detect_peaks',
                         settings.AUTO_DETECT_PEAKS_DEFAULT)

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax
        ax.figure.set_constrained_layout(True)
        ax.set_xlabel("Frequency [1/m]")
        ax.set_ylabel(f"Amplitude [{self.measurement.units[self.channel]}]")

        if settings.SPECTRUM_MINOR_GRID:
            ax.grid(True, which='both')
            ax.minorticks_on()
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(4))
            ax.grid(True, which='minor', linestyle=':', linewidth=0.5)
        else:
            ax.grid()

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.measurement.measurement_label} ({
                self.channel}) - Spectrum")

        overlap_per = self.overlap
        noverlap = round(self.nperseg) * overlap_per

        # Extract the segment of data for analysis
        if self.window_type == "MD":
            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel)
            self.low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')
            self.data = self.measurement.channel_df[self.channel][self.low_index:self.high_index]

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            f, Pxx = welch(self.data,
                           fs=self.fs,
                           window=self.spectral_window,
                           nperseg=self.nperseg,
                           noverlap=noverlap,
                           scaling='spectrum')

        elif self.window_type == "CD":

            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel)

            self.low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            x = self.measurement.cd_distances[self.low_index:self.high_index]

            unfiltered_data = [
                self.measurement.segments[self.channel][sample_idx][self.low_index:self.high_index]
                for sample_idx in self.selected_samples
            ]

            # Calculate individual power spectra, then use the mean. This to prevent opposite phases canceling each other.
            welches = np.array([
                welch(y, fs=self.fs, window='hann', nperseg=self.nperseg,
                      noverlap=noverlap, scaling='spectrum')
                for y in unfiltered_data
            ])
            f = welches[0][0]
            Pxx = np.mean(welches[:, 1], axis=0)

        f_low_index = np.searchsorted(f, self.frequency_range_low)
        f_high_index = np.searchsorted(
            f, self.frequency_range_high, side='right')
        # Convert power spectral density to amplitude spectrum (sqrt of power)
        amplitude_spectrum = np.sqrt(
            Pxx*2) * settings.SPECTRUM_AMPLITUDE_SCALING

        if self.ax:
            xlim = self.ax.get_xlim()
        else:
            xlim = None

        # Plot the amplitude spectrum

        self.frequencies = f[f_low_index:f_high_index]
        self.amplitudes = amplitude_spectrum[f_low_index:f_high_index]

        ax.plot(self.frequencies, self.amplitudes)
        if settings.SPECTRUM_LOGARITHMIC_SCALE:
            ax.set_yscale("log")
            ax.yaxis.set_major_locator(LogLocator(
                base=10.0, subs=np.arange(1.0, 10.0) * 0.1, numticks=10))

        if ylim:
            ax.set_ylim(bottom=ylim[0], top=ylim[1])

        secax = ax.twiny()

        if self.window_type == "CD" or self.show_wavelength:

            def update_secax(*args):
                primary_ticks = ax.get_xticks()
                secax.set_xticks(primary_ticks)
                secax.set_xlim(*ax.get_xlim())
                secondary_ticks = [100 * (1 / i) for i in secax.get_xticks()]
                secax.set_xticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])

            secax.set_xlabel(f"Wavelength [cm]")

        elif self.window_type == "MD":

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

            # First detect peaks in the full spectrum within peak detection range
            pf_low_index = np.searchsorted(f, self.peak_detection_range_min)
            pf_high_index = np.searchsorted(
                f, self.peak_detection_range_max, side='right')

            # Only proceed with peak detection if we have a valid range
            if pf_high_index > pf_low_index:
                # Slice the full amplitude spectrum for peak detection
                amplitude_spectrum_for_peaks = amplitude_spectrum[pf_low_index:pf_high_index]

                # Detect peaks in the peak detection range
                peaks, properties = find_peaks(amplitude_spectrum_for_peaks)

                # Map peaks back to global frequency indices
                peaks_global = peaks + pf_low_index

                # Sort peaks based on their amplitudes
                sorted_peak_indices = peaks_global[np.argsort(
                    amplitude_spectrum[peaks_global])][::-1]

                # Filter peaks to only include those within the visible range
                visible_peaks = [idx for idx in sorted_peak_indices
                                 if f_low_index <= idx < f_high_index]

                if settings.MULTIPLE_SELECT_MODE:
                    top_peaks = visible_peaks[:settings.SPECTRUM_AUTO_DETECT_PEAKS]
                else:
                    top_peaks = visible_peaks[:1]

                # Convert peak indices to frequencies
                self.selected_freqs = [f[peak] for peak in top_peaks]
            else:
                self.selected_freqs = []

        # Draw new lines and update frequency label
        if len(self.selected_freqs) > 0:

            # legend_columns = [f"Amplitude [{self.measurement.units[self.channel]}]",
            #                   "Frequency [1/m]", "Wavelength [cm]", "Frequency [Hz]"]
            if self.window_type == "MD":
                legend_columns = [f"A [{self.measurement.units[self.channel]}]",
                                  "F [1/m]", "λ [cm]", "F [Hz]"]
            if self.window_type == "CD":
                legend_columns = [f"A [{self.measurement.units[self.channel]}]",
                                  "F [1/m]", "λ [cm]"]

            legend_data = []

            xlim = ax.get_xlim()
            if settings.MULTIPLE_SELECT_MODE:

                for i, selected_freq in enumerate(self.selected_freqs):

                    if (selected_freq > xlim[1]) or (selected_freq < xlim[0]):
                        continue

                    amplitude = self.amplitudes[np.searchsorted(
                        self.frequencies, selected_freq)]

                    if self.window_type == "CD":
                        label = f"{selected_freq:.2f} 1/m λ = {100 *
                                                               1/selected_freq:.2f} cm A = {amplitude:.2f} {self.measurement.units[self.channel]}"
                        print(f"Spectral peak in {self.channel}: {label}")
                        legend_data.append([f"{amplitude:.2f}", f"{selected_freq:.2f}", f"{
                                           100*(1/selected_freq):.2f}"])
                    elif self.window_type == "MD":
                        label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                            100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.measurement.units[self.channel]}"
                        print(f"Spectral peak in {self.channel}: {label}")

                        legend_data.append([f"{amplitude:.3f}", f"{selected_freq:.2f}", f"{
                                           100*(1/selected_freq):.2f}", f"{self.get_freq_in_hz(selected_freq):.2f}"])
                        print(f"Spectral peak in {self.channel}: {label}")

                    def get_color_cycler(num_colors):
                        # You can change 'tab10' to any colormap you prefer
                        cmap = plt.get_cmap('tab10')
                        colors = [cmap(i) for i in range(num_colors)]
                        return colors

                    num_lines = len(self.selected_freqs)
                    color_cycle = get_color_cycler(num_lines)

                    vl = ax.axvline(x=selected_freq,
                                    linestyle='--',
                                    alpha=0.5,
                                    color=color_cycle[i % num_lines],
                                    label=label)
                    self.current_vlines.append(vl)

            else:
                for i in range(1, 1+settings.MAX_HARMONICS_DISPLAY):
                    if (self.selected_freqs[-1] * i > xlim[1]) or (self.selected_freqs[-1] * i < xlim[0]):
                        # Skip drawing the line if it is out of bounds
                        continue

                    # TODO: DRY, fix this and refactor
                    selected_freq = self.selected_freqs[-1]
                    amplitude = self.amplitudes[np.searchsorted(
                        self.frequencies, selected_freq)]

                    if (i == 1):
                        if self.window_type == "CD":
                            label = f"{selected_freq:.2f} 1/m λ = {100 * 1/selected_freq:.2f} cm A = {
                                amplitude:.2f} {self.measurement.units[self.channel]}"
                            print(f"Spectral peak in {self.channel}: {label}")
                        elif self.window_type == "MD":
                            label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                                100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.measurement.units[self.channel]}"
                            print(f"Spectral peak in {self.channel}: {label}")
                    else:
                        label = None

                    vl = ax.axvline(x=self.selected_freqs[-1] * i,
                                    color='r',
                                    linestyle='--',
                                    alpha=1 -
                                    (1 / settings.MAX_HARMONICS_DISPLAY) * i,
                                    label=label)
                    self.current_vlines.append(vl)

                    # Draw harmonic number below the line
                    if settings.SPECTRUM_SHOW_HARMONICS_NUMBERS:
                        harmonic_x = self.selected_freqs[-1] * i
                        ymin, ymax = ax.get_ylim()
                        txt = ax.text(
                            harmonic_x,
                            # Slightly above the bottom
                            ymin + 0.02 * (ymax - ymin),
                            f"{i}",
                            ha='center',
                            va='bottom',
                            fontsize=8,
                            color="tab:gray",
                            alpha=0.8
                        )
                        txt.set_path_effects([
                            path_effects.Stroke(linewidth=2, foreground='white'),
                            path_effects.Normal()
                        ])

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        for index, element in enumerate(self.selected_elements):
            xlim = ax.get_xlim()
            for i in range(1, settings.MAX_HARMONICS_DISPLAY):
                f = element["spatial_frequency"]
                if (f * i > xlim[1]) or (f * i < xlim[0]):
                    continue
                label = None
                if i == 1:
                    name = element.get("name", "Element")
                    freq = f
                    wavelength = 1 / freq if freq else None
                    amplitude = None
                    # Find amplitude at this frequency if possible
                    if hasattr(self, "frequencies") and hasattr(self, "amplitudes") and freq:
                        freq_idx = np.searchsorted(self.frequencies, freq)
                        if 0 <= freq_idx < len(self.amplitudes):
                            amplitude = self.amplitudes[freq_idx]
                    if self.window_type == "MD":
                        freq_hz = freq * self.machine_speed / 60 if freq else None
                        label = f"{name}: {freq:.2f} 1/m {freq_hz:.2f} Hz λ = {100*wavelength:.2f} cm"
                        if amplitude is not None:
                            label += f" A = {amplitude:.2f} {self.measurement.units[self.channel]}"
                    else:
                        label = f"{name}: {freq:.2f} 1/m λ = {100*wavelength:.2f} cm"
                        if amplitude is not None:
                            label += f" A = {amplitude:.2f} {self.measurement.units[self.channel]}"
                color_index = index % len(colors)
                current_color = colors[color_index]
                vl = ax.axvline(x=f * i,
                                linestyle='--',
                                alpha=1 -
                                (1 / settings.MAX_HARMONICS_DISPLAY) * i,
                                label=label,
                                color=current_color)
                self.current_vlines.append(vl)
        handles, labels = ax.get_legend_handles_labels()

        if settings.SPECTRUM_SHOW_LEGEND:
            if labels:  # This list will be non-empty if there are items to include in the legend
                if settings.SPECTRUM_LEGEND_OUTSIDE_PLOT:
                    leg = tabular_legend(ax, legend_columns, legend_data, loc="upper left", bbox_to_anchor=(
                        1.05, 1), borderaxespad=0.)

                    leg.get_frame().set_alpha(0)
                else:
                    ax.legend(handles, labels, loc="upper right")

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def get_freq_in_hz(self, freq_1m):
        return freq_1m * self.machine_speed / 60

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
            f"{self.channel} amplitude [{self.measurement.units[self.channel]}]": self.amplitudes
        }

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin,
                     SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin, CopyPlotMixin, AutoDetectPeaksMixin,
                     ChildWindowCloseMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.paperMachineDataWindow = None
        self.sosAnalysisWindow = None
        self.sosAnalysis = None
        self.sampleSelectorWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self):
        exportAction = self.controller.initExportAction(
            self, "Export spectrum")
        self.file_menu.addAction(exportAction)

        viewMenu = self.menu_bar.addMenu('View')

        self.paperMachineDataAction = QAction('Paper machine data', self)
        self.sosAnalysisAction = QAction('SOS analysis', self)

        if 'sos' not in store.analyses:
            self.sosAnalysisAction.setDisabled(True)

        if not self.measurement.pm_data:
            self.paperMachineDataAction.setDisabled(True)
        viewMenu.addAction(self.paperMachineDataAction)

        if self.window_type == "MD":
            viewMenu.addAction(self.sosAnalysisAction)

        if self.window_type == "CD":
            self.selectSamplesAction = QAction('Select samples', self)
            viewMenu.addAction(self.selectSamplesAction)
            self.selectSamplesAction.triggered.connect(
                self.toggleSelectSamples)

        self.paperMachineDataAction.setCheckable(True)
        self.sosAnalysisAction.setCheckable(True)
        self.paperMachineDataAction.triggered.connect(
            self.togglePaperMachineData)
        self.sosAnalysisAction.triggered.connect(self.toggleSOSAnalysis)

    def togglePaperMachineData(self, checked):
        if self.paperMachineDataWindow is None:
            self.paperMachineDataWindow = PaperMachineDataWindow(
                self.updateElements, self.window_type, self.checked_elements, self.measurement)
            self.paperMachineDataWindow.show()
            selected_freq = self.controller.selected_freqs[-1] if self.controller.selected_freqs else None
            self.paperMachineDataWindow.refresh_pm_data(
                self.controller.machine_speed, selected_freq)
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

    def refreshSOS(self):
        if self.sosAnalysis:
            self.sosAnalysis.controller.data = self.controller.data
            self.sosAnalysis.controller.fs = self.controller.fs
            self.sosAnalysis.controller.selected_freqs = self.controller.selected_freqs
            self.sosAnalysis.controller.channel = self.controller.channel
            self.sosAnalysis.window.refresh()

    def toggleSOSAnalysis(self, checked):
        if self.sosAnalysisWindow is None:
            self.sosAnalysis = Analysis(
                self.measurement, 'sos', self.window_type)
            self.sosAnalysisWindow = self.sosAnalysis.window
            self.sosAnalysisWindow.show()
            self.sosAnalysisWindow.closed.connect(self.onSOSAnalysisClosed)
            self.controller.updated.connect(self.refreshSOS)
            self.sosAnalysisAction.setChecked(True)
        else:
            self.sosAnalysisWindow.close()

    def onSOSAnalysisClosed(self):
        self.sosAnalysisWindow = None
        self.sosAnalysisAction.setChecked(False)

    def initUI(self):
        self.setWindowTitle(
            f"{analysis_name} ({self.controller.window_type}) - {self.measurement.measurement_label}")
        self.resize(*settings.SPECTRUM_WINDOW_SIZE)

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(
            self.controlsPanel, 0)  # Controls take less space

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        self.controlsPanel.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)

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

        if self.controller.window_type == "MD":
            self.addShowWavelengthCheckbox(displayOptionsLayout)

        self.addAutoDetectPeaksCheckbox(displayOptionsLayout)

        self.refineButton = QPushButton("Refine Frequency Selection")
        self.refineButton.clicked.connect(self.refineFrequency)
        displayOptionsLayout.addWidget(self.refineButton)

        self.clearButton = QPushButton("Clear Frequency Selection")
        self.clearButton.clicked.connect(self.clearFrequency)
        displayOptionsLayout.addWidget(self.clearButton)

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        # Plot/stats take more space
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Add selected frequency label
        self.selectedFrequencyLabel = QLabel("Selected frequency: None")
        plotStatsLayout.addWidget(self.selectedFrequencyLabel)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)
        self.controller.canvas.mpl_connect('button_press_event', self.onclick)

        self.refresh()

    def clearFrequency(self):
        self.controller.selected_freqs = []
        self.selectedFrequencyLabel.setText(f"Selected frequency:")

        self.refresh()

    def refineFrequency(self):
        selected_freqs = self.controller.selected_freqs
        if not selected_freqs:
            print("No selected frequency")
            return

        print("Original frequency: ", selected_freqs[-1])
        d = self.measurement.channel_df[self.controller.channel][self.controller.low_index:self.controller.high_index]
        import time
        start_time = time.time()  # Capture start time

        plot_min = self.controller.ax.get_xlim()[0] if self.controller.ax.get_xlim()[
            0] > 0 else 0
        plot_max = self.controller.ax.get_xlim()[1]
        wrange = (plot_max - plot_min) * 0.01

        refined = hs_units(
            d, self.controller.fs, selected_freqs[-1], wrange, plot_min, plot_max, settings.MAX_HARMONICS_FREQUENCY_ESTIMATOR)

        print(self.controller.fs)
        # Todo: Only search withing the visible window
        end_time = time.time()  # Capture end time
        # Calculate elapsed time in milliseconds
        elapsed_time_ms = (end_time - start_time) * 1000
        # Print elapsed time
        print(f"Fundamental frequency estimation took {
              elapsed_time_ms:.2f} ms")
        print("Refined frequency: ", refined)
        self.controller.selected_freqs[-1] = refined
        self.refresh()

        if self.sosAnalysisWindow:
            self.sosAnalysisWindow.refresh()

    def onclick(self, event):
        # Frequency selector functionality with axis limit check and label update
        if event.inaxes is not None and event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:

            ax = event.inaxes

            # Check if the x-coordinate is within the axis limits
            xlim = ax.get_xlim()
            if not (xlim[0] <= event.xdata <= xlim[1]) or event.xdata < 0:
                return  # Do not proceed if the x-coordinate is out of bounds
            if not self.controller.selected_freqs:
                self.controller.selected_freqs = []

            self.controller.selected_freqs.append(event.xdata)
            self.refresh(restore_lim=True)
            if self.sosAnalysisWindow:
                self.sosAnalysisWindow.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        self.initFrequencyRangeSlider(block_signals=True)
        self.initSpectrumLengthSlider(block_signals=True)
        if self.window_type == "MD":
            self.initShowWavelengthCheckbox(block_signals=True)
            self.initMachineSpeedSpinner(block_signals=True)

    def refresh(self, restore_lim=False):
        self.controller.updatePlot()
        self.refresh_widgets()
        selected_freqs = self.controller.selected_freqs

        machine_speed = self.controller.machine_speed
        if self.controller.selected_freqs:
            wavelength = 1 / self.controller.selected_freqs[-1]

            if self.window_type == "MD":
                frequency_in_hz = selected_freqs[-1] * machine_speed / 60
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {
                        selected_freqs[-1]:.2f} 1/m ({frequency_in_hz:.2f} Hz) λ = {100*wavelength:.2f} cm"
                )

            elif self.window_type == "CD":
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freqs[-1]:.2f} 1/m (λ = {100*wavelength:.2f} cm)")

        if self.paperMachineDataWindow:
            self.paperMachineDataWindow.refresh_pm_data(
                machine_speed, selected_freqs[-1] if selected_freqs else None)
