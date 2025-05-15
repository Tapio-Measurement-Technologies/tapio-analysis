from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QPushButton, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
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
    ExportMixin
)
from gui.paper_machine_data import PaperMachineDataWindow
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from scipy.signal import welch
import numpy as np
import pandas as pd
import settings

analysis_name = "Cepstrum"
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
    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
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

        self.fs = 1 / self.measurement.sample_step
        config = spectrum_defaults[self.window_type]
        self.nperseg = config["nperseg"]
        self.overlap = config["overlap"]
        self.max_freq = self.fs / 2
        self.frequency_range_low = self.max_freq * config["range_min"]
        self.frequency_range_high = self.max_freq * config["range_max"]

        self.peak_detection_range_min = config["peak_detection_range_min"]
        self.peak_detection_range_max = config["peak_detection_range_max"]

        self.spectrum_length_slider_min = config["spectrum_length_slider_min"]
        self.spectrum_length_slider_max = config["spectrum_length_slider_max"]

        self.max_dist = np.max(
            self.measurement.cd_distances if self.window_type == "CD" else self.measurement.distances)

        self.analysis_range_low = config["analysis_range_low"] * self.max_dist
        self.analysis_range_high = config["analysis_range_high"] * \
            self.max_dist

        self.machine_speed = settings.PAPER_MACHINE_SPEED_DEFAULT

        self.selected_elements = []
        self.selected_samples = self.measurement.selected_samples.copy()
        self.selected_freqs = []
        self.show_wavelength = settings.SHOW_WAVELENGTH_DEFAULT
        self.auto_detect_peaks = settings.AUTO_DETECT_PEAKS_DEFAULT

        self.current_vlines = []

        self.spectral_window = settings.SPECTRUM_WELCH_WINDOW

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax

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

        # --- CEPSTRUM CALCULATION AND PLOTTING ---
        # Use the extracted data segment for cepstrum calculation
        if self.window_type == "MD":
            data_for_cepstrum = self.data
        else:  # CD
            data_for_cepstrum = np.mean(unfiltered_data, axis=0)

        # Calculate real cepstrum
        spectrum = np.fft.fft(data_for_cepstrum)
        log_spectrum = np.log(np.abs(spectrum) + 1e-12)  # avoid log(0)
        cepstrum = np.fft.ifft(log_spectrum).real

        # Quefrency axis (in meters)
        quefrency = np.arange(len(cepstrum)) * self.measurement.sample_step

        # Plot only the first half (up to Nyquist quefrency)
        N = len(cepstrum) // 2
        ax.plot(quefrency[:N], cepstrum[:N])
        ax.set_xlabel("Quefrency [m]")
        ax.set_ylabel("Cepstrum amplitude")

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.measurement.measurement_label} ({self.channel}) - Cepstrum")

        ax.grid(True)
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
        self.sampleSelectorWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        fileMenu = menuBar.addMenu('File')
        exportAction = self.controller.initExportAction(
            self, "Export cepstrum")
        fileMenu.addAction(exportAction)

        viewMenu = menuBar.addMenu('View')

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
                self.controller.machine_speed, selected_freq)
            self.paperMachineDataWindow.closed.connect(
                self.onPaperMachineDataClosed)
            self.paperMachineDataAction.setChecked(True)
            self.pmdButton.setChecked(True)
        else:
            self.paperMachineDataWindow.close()

    def updateElements(self, selected_elements=None):
        self.checked_elements = selected_elements
        self.controller.selected_elements = selected_elements
        self.refresh()

    def onPaperMachineDataClosed(self):
        self.paperMachineDataWindow = None
        self.paperMachineDataAction.setChecked(False)
        self.pmdButton.setChecked(False)

    def initUI(self):
        self.setWindowTitle(f"{analysis_name} ({self.controller.window_type}) - {self.measurement.measurement_label}")
        self.setGeometry(150, 150, 1000, 600) # Default geometry, recommend CEPSTRUM_WINDOW_GEOMETRY

        # Top-level layout for menu bar and main content
        topLevelLayout = QVBoxLayout()
        self.setLayout(topLevelLayout)

        self.initMenuBar(topLevelLayout)

        # Main horizontal layout for controls and plot
        mainHorizontalLayout = QHBoxLayout()
        topLevelLayout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        controlsPanelLayout = QVBoxLayout()
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(settings.ANALYSIS_CONTROLS_PANEL_MIN_WIDTH)
        controlsWidget.setLayout(controlsPanelLayout)
        mainHorizontalLayout.addWidget(controlsWidget, 0)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        controlsPanelLayout.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)

        # Analysis Parameters Group (using Spectrum-like controls as per original structure)
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addFrequencyRangeSlider(analysisParamsLayout) # Cepstrum uses freq range from spectrum defaults
        self.addSpectrumLengthSlider(analysisParamsLayout)
        if self.controller.window_type == "MD":
            self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display Options Group (some may be less relevant for pure cepstrum but in template)
        displayOptionsGroup = QGroupBox("Display && Peak Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        controlsPanelLayout.addWidget(displayOptionsGroup)
        if self.controller.window_type == "MD":
            self.addShowWavelengthCheckbox(displayOptionsLayout)

        self.clearButton = QPushButton("Clear Quefrency Selection") # Adapted label
        self.clearButton.clicked.connect(self.clearFrequency)
        displayOptionsLayout.addWidget(self.clearButton)

        self.refineButton = QPushButton("Refine Quefrency Selection") # Adapted label
        self.refineButton.clicked.connect(self.refineFrequency)
        displayOptionsLayout.addWidget(self.refineButton)

        # Other Toggles Group
        if self.controller.window_type == "MD":
            otherTogglesGroup = QGroupBox("Other Analyses")
            otherTogglesLayout = QVBoxLayout()
            otherTogglesGroup.setLayout(otherTogglesLayout)
            controlsPanelLayout.addWidget(otherTogglesGroup)

            self.pmdButton = QPushButton("Paper Machine Data")
            self.pmdButton.setCheckable(True)
            self.pmdButton.clicked.connect(self.togglePaperMachineData)
            if not self.measurement.pm_data:
                self.pmdButton.setDisabled(True)
            otherTogglesLayout.addWidget(self.pmdButton)

        controlsPanelLayout.addStretch()

        # Right panel for plot
        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        # Quefrency Label (from original UI)
        self.selectedQuefrencyLabel = QLabel("Selected quefrency: None")
        plotLayout.addWidget(self.selectedQuefrencyLabel) # Place it above plot in the right panel

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        self.plot.mpl_connect('button_press_event', self.onclick)
        plotLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        plotLayout.addWidget(self.toolbar)

        self.refresh()

    def clearFrequency(self):
        self.controller.selected_freqs = []
        self.selectedQuefrencyLabel.setText(f"Selected quefrency:")

        self.refresh()

    def refineFrequency(self):
        selected_freqs = self.controller.selected_freqs
        if not selected_freqs:
            print("No selected quefrency")
            return

        print("Original quefrency: ", selected_freqs[-1])
        d = self.measurement.channel_df[self.controller.channel][self.controller.low_index:self.controller.high_index]
        import time
        start_time = time.time()

        plot_min = self.controller.ax.get_xlim()[0] if self.controller.ax.get_xlim()[0] > 0 else 0
        plot_max = self.controller.ax.get_xlim()[1]
        wrange = (plot_max - plot_min) * 0.01

        refined = selected_freqs[-1]
        print(f"Fundamental quefrency estimation (hs_units) might not be applicable here. Original value kept.")

        end_time = time.time()
        elapsed_time_ms = (end_time - start_time) * 1000
        print(f"Refinement step took {elapsed_time_ms:.2f} ms (currently no actual refinement for cepstrum)")
        print("Refined quefrency: ", refined)
        self.controller.selected_freqs[-1] = refined
        self.refresh()

    def onclick(self, event):
        if event.inaxes is not None and event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:
            ax = event.inaxes
            xlim = ax.get_xlim()
            if not (xlim[0] <= event.xdata <= xlim[1]) or event.xdata < 0:
                return
            if not self.controller.selected_freqs:
                self.controller.selected_freqs = []
            self.controller.selected_freqs.append(event.xdata)
            self.refresh(restore_lim=True)

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

        if selected_freqs:
            selected_quefrency_m = selected_freqs[-1]
            self.selectedQuefrencyLabel.setText(
                f"Selected quefrency: {selected_quefrency_m:.4f} m"
            )
        else:
            self.selectedQuefrencyLabel.setText("Selected quefrency: None")

        if self.paperMachineDataWindow:
            self.paperMachineDataWindow.refresh_pm_data(
                machine_speed, None)