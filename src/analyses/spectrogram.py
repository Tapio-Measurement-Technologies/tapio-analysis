from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import hs_units
import matplotlib.pyplot as plt
import matplotlib
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    FrequencyRangeMixin,
    MachineSpeedMixin,
    SampleSelectMixin,
    SpectrumLengthMixin,
    ShowWavelengthMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin
)
from gui.paper_machine_data import PaperMachineDataWindow
from utils import store
import settings
import numpy as np

analysis_name = "Spectrogram"
analysis_types = ["MD", "CD"]

class AnalysisController(AnalysisControllerBase):
    nperseg: float
    overlap: float
    frequency_range_low: float
    frequency_range_high: float
    spectrum_length_slider_min: float
    spectrum_length_slider_max: float
    analysis_range_low: float
    analysis_range_high: float
    machine_speed: float
    selected_elements: list[dict]
    selected_samples: list[int]
    selected_freqs: list[float]
    show_wavelength: bool

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.ax = None

        # Dynamic initialization based on window type
        spectrum_defaults = {
            "MD": {
                "nperseg": settings.MD_SPECTROGRAM_DEFAULT_LENGTH,
                "range_min": settings.MD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.MD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.MD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.MD_SPECTROGRAM_OVERLAP,
                "spectrum_length_slider_min": settings.MD_SPECTROGRAM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.MD_SPECTROGRAM_LENGTH_SLIDER_MAX
            },
            "CD": {
                "nperseg": settings.CD_SPECTROGRAM_DEFAULT_LENGTH,
                "range_min": settings.CD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.CD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.CD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.CD_SPECTROGRAM_OVERLAP,
                "spectrum_length_slider_min": settings.CD_SPECTROGRAM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.CD_SPECTROGRAM_LENGTH_SLIDER_MAX
            }
        }
        config = spectrum_defaults[self.window_type]
        self.current_hlines = []

        self.set_default('nperseg', config["nperseg"])
        self.set_default('overlap', config["overlap"])
        self.set_default('frequency_range_low', self.max_freq * config["range_min"])
        self.set_default('frequency_range_high', self.max_freq * config["range_max"])
        self.set_default('spectrum_length_slider_min', config["spectrum_length_slider_min"])
        self.set_default('spectrum_length_slider_max', config["spectrum_length_slider_max"])
        self.set_default('analysis_range_low', config["analysis_range_low"] * self.max_dist)
        self.set_default('analysis_range_high', config["analysis_range_high"] * self.max_dist)
        self.set_default('machine_speed', settings.PAPER_MACHINE_SPEED_DEFAULT)
        self.set_default('selected_elements', [])
        self.set_default('selected_samples', self.measurement.selected_samples.copy())
        self.set_default('selected_freqs', [])
        self.set_default('show_wavelength', False)

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax

        overlap_per = self.overlap
        noverlap = round(self.nperseg * overlap_per)

        # Extract the segment of data for analysis
        if self.window_type == "MD":
            self.low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')
            self.data = self.measurement.channel_df[self.channel][self.low_index:self.high_index]

            if self.nperseg >= (self.high_index-self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return
            data_mean_removed = self.data - np.mean(self.data)

            Pxx, freqs, bins, im = ax.specgram(data_mean_removed,
                                               NFFT=self.nperseg,
                                               Fs=self.fs,
                                               noverlap=noverlap,
                                               window=np.hanning(self.nperseg))

        elif self.window_type == "CD":
            self.low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            if self.nperseg >= (self.high_index-self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return

            x = self.measurement.cd_distances[self.low_index:self.high_index]

            unfiltered_data = [self.measurement.segments[self.channel][sample_idx]
                               [self.low_index:self.high_index] for sample_idx in self.selected_samples]
            mean_profile = np.mean(unfiltered_data, axis=0)
            mean_profile = mean_profile - np.mean(mean_profile)


            Pxx, freqs, bins, im = ax.specgram(mean_profile,
                                               NFFT=self.nperseg,
                                               Fs=self.fs,
                                               noverlap=noverlap,
                                               window=np.hanning(self.nperseg))



        amplitudes = np.sqrt(Pxx*2) * settings.SPECTRUM_AMPLITUDE_SCALING
        freq_indices = (freqs >= self.frequency_range_low) & (
            freqs <= self.frequency_range_high)
        freqs_cut = freqs[freq_indices]
        amplitudes_cut = amplitudes[freq_indices, :]
        im = ax.imshow(amplitudes_cut, aspect='auto', origin='lower',
                       extent=[bins[0], bins[-1], freqs_cut[0], freqs_cut[-1]],
                       norm=matplotlib.colors.Normalize(vmin=0, vmax=3*np.mean(amplitudes_cut)), cmap=settings.SPECTROGRAM_COLORMAP)

        # Set the axis labels, title, and colorbar
        ax.set_title(f"{self.measurement.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel("Frequency [1/m]")
        cbar = self.figure.colorbar(im, ax=ax, pad=0.2)
        cbar.set_label(f"Amplitude [{self.measurement.units[self.channel]}]")

        secax = ax.twinx()

        if self.window_type == "CD" or self.show_wavelength:
            def update_secax(*args):
                primary_ticks = ax.get_yticks()
                secax.set_yticks(primary_ticks)
                secax.set_ylim(*ax.get_ylim())
                secondary_ticks = [100*(1 / i) for i in secax.get_yticks()]
                secax.set_yticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])
            secax.set_ylabel(f"Wavelength [cm]")

        elif self.window_type == "MD":
            def update_secax(*args):
                primary_ticks = ax.get_yticks()
                secax.set_yticks(primary_ticks)
                secax.set_ylim(*ax.get_ylim())
                secondary_ticks = secax.get_yticks() * self.machine_speed / 60
                secax.set_yticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])
            secax.set_ylabel(
                f"Frequency [Hz] at machine speed {self.machine_speed:.1f} m/min")

        ax.set_zorder(secax.get_zorder() + 1)
        update_secax()  # Initial call to update secondary axis

        # Update secondary axis on primary axis changes
        ax.callbacks.connect('xlim_changed', update_secax)
        ax.figure.canvas.mpl_connect('resize_event', update_secax)

        # Draw new lines and update frequency label
        if self.selected_freqs:

            ylim = ax.get_ylim()

            for i in range(1, settings.MAX_HARMONICS_DISPLAY):
                if (self.selected_freqs[-1] * i > ylim[1]) or (self.selected_freqs[-1] * i < ylim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue

                label = "Selected frequency" if (i == 1) else None
                hl = ax.axhline(y=self.selected_freqs[-1] * i,
                                color='r', linestyle='--', alpha=1 - (1/settings.MAX_HARMONICS_DISPLAY) * i, label=label)
                self.current_hlines.append(hl)

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        for index, element in enumerate(self.selected_elements):
            ylim = ax.get_ylim()
            for i in range(1, settings.MAX_HARMONICS_DISPLAY):
                f = element["spatial_frequency"]
                if (f * i > ylim[1]) or (f * i < ylim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue
                label = element["name"] if (i == 1) else None
                color_index = index % len(colors)
                current_color = colors[color_index]

                hlw = ax.axhline(y=f * i, color='white', linestyle='-',
                                 alpha=0.8*(1-i*1/settings.MAX_HARMONICS_DISPLAY))
                self.current_hlines.append(hlw)

                hl=ax.axhline(y=f * i, linestyle='--', alpha=1 -
                                (1/settings.MAX_HARMONICS_DISPLAY) * i, label=label, color=current_color)
                self.current_hlines.append(hl)
        handles, labels=ax.get_legend_handles_labels()
        if labels:  # This list will be non-empty if there are items to include in the legend
            ax.legend(handles, labels, loc="upper right")

        # ax.figure.set_constrained_layout(True)
        # ax.grid()
        # ax.tight_layout()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        if self.selected_freqs[-1]:
            wavelength = 1 / self.selected_freqs[-1]
            stats.append(["Selected frequency:", ""])
            if self.window_type == "MD":
                frequency_in_hz = self.selected_freqs[-1] * self.machine_speed / 60
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freqs[-1]:.2f} 1/m ({frequency_in_hz:.2f} Hz)\n{100*wavelength:.2f} m"])
            elif self.window_type == "CD":
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freqs[-1]:.2f} 1/m\n{100*wavelength:.3f} m"
                ])
        return stats


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin, SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin, CopyPlotMixin, ChildWindowCloseMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)

        self.paperMachineDataWindow = None
        self.sampleSelectorWindow = None
        self.sosAnalysisWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self):
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

    def refreshSOS(self):
        self.sosAnalysis.controller.data = self.controller.data
        self.sosAnalysis.controller.fs = self.controller.fs
        self.sosAnalysis.controller.selected_freqs = self.controller.selected_freqs
        self.sosAnalysis.controller.channel = self.controller.channel
        self.sosAnalysis.controller.low_index = self.controller.low_index
        self.sosAnalysis.controller.high_index = self.controller.high_index
        self.sosAnalysis.window.refresh()

    def toggleSOSAnalysis(self, checked):
        if self.sosAnalysisWindow is None:
            self.sosAnalysis = store.analyses['sos'].Analysis(self.measurement, self.window_type)
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

    def updateSpectrumLength(self, value):
        self.controller.nperseg = value  # Update your nperseg value based on the slider
        self.refresh()  # Refresh the plot with the new spectrum length

    def initUI(self):
        self.setWindowTitle(f"{analysis_name} ({self.controller.window_type}) - {self.measurement.measurement_label}")
        self.setGeometry(*settings.SPECTROGRAM_WINDOW_GEOMETRY) # Default geometry, consider adding to settings.py

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

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

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addFrequencyRangeSlider(analysisParamsLayout)
        self.addSpectrumLengthSlider(analysisParamsLayout)
        if self.controller.window_type == "MD":
            self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display Options Group
        displayOptionsGroup = QGroupBox("Display Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        controlsPanelLayout.addWidget(displayOptionsGroup)
        if self.controller.window_type == "MD":
            self.addShowWavelengthCheckbox(displayOptionsLayout)

        self.selectedFrequencyLabel = QLabel("Selected frequency: None") # Keep this label as it's updated in onclick
        displayOptionsLayout.addWidget(self.selectedFrequencyLabel)

        self.clearButton = QPushButton("Clear Frequency Selection")
        self.clearButton.clicked.connect(self.clearFrequency)
        displayOptionsLayout.addWidget(self.clearButton)


        if self.controller.window_type == "MD":
            otherTogglesGroup = QGroupBox("Other Analyses")
            otherTogglesLayout = QVBoxLayout()
            otherTogglesGroup.setLayout(otherTogglesLayout)
            controlsPanelLayout.addWidget(otherTogglesGroup)

            self.sosButton = QPushButton("SOS Analysis")
            self.sosButton.setCheckable(True)
            self.sosButton.clicked.connect(self.toggleSOSAnalysis)
            otherTogglesLayout.addWidget(self.sosButton)

            self.pmdButton = QPushButton("Paper Machine Data")
            self.pmdButton.setCheckable(True)
            self.pmdButton.clicked.connect(self.togglePaperMachineData)
            if not self.measurement.pm_data:
                self.pmdButton.setDisabled(True)
            otherTogglesLayout.addWidget(self.pmdButton)

        controlsPanelLayout.addStretch()

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)
        self.controller.canvas.mpl_connect('button_press_event', self.onclick)

        self.refresh()

    def clearFrequency(self):
        self.controller.selected_freqs = []
        self.selectedFrequencyLabel.setText(
            f"Selected frequency:")
        self.refresh()

    def refineFrequency(self):
        if not self.controller.selected_freqs:
            print("No selected frequency")
            return

        print("Original frequency: ", self.controller.selected_freqs[-1])
        d = self.measurement.channel_df[self.controller.channel][self.controller.low_index:self.controller.high_index]
        import time
        start_time = time.time()  # Capture start time

        plot_min = self.controller.ax.get_ylim()[0] if self.controller.ax.get_ylim()[
            0] > 0 else 0
        plot_max = self.controller.ax.get_ylim()[1]
        wrange = (plot_max - plot_min) * 0.01

        refined = hs_units(d, self.controller.fs, self.controller.selected_freqs[-1],
                           wrange, plot_min, plot_max, settings.MAX_HARMONICS_DISPLAY)

        print(self.controller.fs)
        # Todo: Only search withing the visible window
        end_time = time.time()  # Capture end time
        # Calculate elapsed time in milliseconds
        elapsed_time_ms = (end_time - start_time) * 1000
        # Print elapsed time
        print(
            f"Fundamental frequency estimation took {elapsed_time_ms:.2f} ms")
        print("Refined frequency: ", refined)
        self.controller.selected_freqs[-1] = refined
        self.refresh()

    def onclick(self, event):
        # Frequency selector functionality with axis limit check and label update
        if event.inaxes is not None and event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:

            ax = event.inaxes

            # Check if the x-coordinate is within the axis limits
            ylim = ax.get_ylim()
            if not (ylim[0] <= event.ydata <= ylim[1]) or event.ydata < 0:
                return  # Do not proceed if the x-coordinate is out of bounds

            if not self.controller.selected_freqs:
                self.controller.selected_freqs = []
            self.controller.selected_freqs.append(event.ydata)
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
        machine_speed = self.controller.machine_speed
        selected_freqs = self.controller.selected_freqs
        if selected_freqs:
            wavelength = 1 / selected_freqs[-1]
            if self.window_type == "MD":
                frequency_in_hz = selected_freqs[-1] * machine_speed / 60
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freqs[-1]:.2f} 1/m ({frequency_in_hz:.2f} Hz) λ = {100*wavelength:.2f} cm")

            elif self.window_type == "CD":
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freqs[-1]:.2f} 1/m (λ = {100*wavelength:.2f} cm)")

        if self.paperMachineDataWindow:

            selected_freq = selected_freqs[-1] if selected_freqs else None
            self.paperMachineDataWindow.refresh_pm_data(
                machine_speed, selected_freq)
