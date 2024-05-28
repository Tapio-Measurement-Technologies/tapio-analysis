from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QPushButton
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from gui.components import AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin, SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin
from utils.data_loader import DataMixin
from gui.paper_machine_data import PaperMachineDataWindow
from gui.sos_analysis import SOSAnalysisWindow
from utils.signal_processing import hs_units
from controllers import SpectrogramController
import settings


class SpectrogramWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin, SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin):

    def __init__(self, window_type="MD", controller: SpectrogramController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else SpectrogramController()
        self.window_type = window_type
        self.paperMachineDataWindow = None
        self.sampleSelectorWindow = None
        self.sosAnalysisWindow = None
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)

        viewMenu = menuBar.addMenu('View')

        self.paperMachineDataAction = QAction('Paper machine data', self)
        self.sosAnalysisAction = QAction('SOS analysis', self)

        disable_pm_action = not hasattr(self.dataMixin, 'pm_data')
        self.paperMachineDataAction.setDisabled(disable_pm_action)
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
                self.updateElements, self.window_type)
            self.paperMachineDataWindow.show()
            self.paperMachineDataWindow.refresh_pm_data(self.controller.machine_speed)
            self.paperMachineDataWindow.closed.connect(
                self.onPaperMachineDataClosed)
            self.paperMachineDataAction.setChecked(True)
        else:
            self.paperMachineDataWindow.close()

    def updateElements(self, selected_elements=None):
        self.controller.selected_elements = selected_elements
        self.refresh()

    def onPaperMachineDataClosed(self):
        self.paperMachineDataWindow = None
        self.paperMachineDataAction.setChecked(False)

    def refreshSOS(self):
        pass

    def toggleSOSAnalysis(self, checked):
        if self.sosAnalysisWindow is None:
            self.sosAnalysisWindow = SOSAnalysisWindow(self.controller)
            self.sosAnalysisWindow.show()
            self.sosAnalysisWindow.closed.connect(self.onSOSAnalysisClosed)
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

        self.setWindowTitle(
            f"{self.window_type} spectrogram ({self.dataMixin.measurement_label})")
        self.setGeometry(200, 200, 950, 950)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)
        self.addChannelSelector(mainLayout)

        self.addAnalysisRangeSlider(mainLayout)
        if self.window_type == "MD":
            self.addMachineSpeedSpinner(mainLayout)

        self.spectrumLengthLabel = QLabel("Window length")
        mainLayout.addWidget(self.spectrumLengthLabel)

        self.addSpectrumLengthSlider(mainLayout)
        self.addFrequencyRangeSlider(mainLayout)

        if self.window_type == "MD":
            self.addShowWavelengthCheckbox(mainLayout)

        self.selectedFrequencyLabel = QLabel("Selected frequency: None")
        mainLayout.addWidget(self.selectedFrequencyLabel)

        self.refineButton = QPushButton("Refine")
        self.refineButton.clicked.connect(self.refineFrequency)
        mainLayout.addWidget(self.refineButton)

        self.clearButton = QPushButton("Clear")
        self.clearButton.clicked.connect(self.clearFrequency)
        mainLayout.addWidget(self.clearButton)

        self.plot = self.controller.plot()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.plot.mpl_connect('button_press_event', self.onclick)

        self.refresh()

    def clearFrequency(self):
        self.controller.selected_freq = None
        self.selectedFrequencyLabel.setText(
            f"Selected frequency:")
        self.refresh()

    def refineFrequency(self):
        if not self.controller.selected_freq:
            print("No selected frequency")
            return

        print("Original frequency: ", self.controller.selected_freq)
        d = self.dataMixin.channel_df[self.controller.channel][self.controller.low_index:self.controller.high_index]
        import time
        start_time = time.time()  # Capture start time

        plot_min = self.controller.ax.get_ylim()[0] if self.controller.ax.get_ylim()[0] > 0 else 0
        plot_max = self.controller.ax.get_ylim()[1]
        wrange = (plot_max - plot_min) * 0.01

        refined = hs_units(d, self.controller.fs, self.controller.selected_freq,
                           wrange, plot_min, plot_max, settings.MAX_HARMONICS)

        print(self.controller.fs)
        # Todo: Only search withing the visible window
        end_time = time.time()  # Capture end time
        # Calculate elapsed time in milliseconds
        elapsed_time_ms = (end_time - start_time) * 1000
        # Print elapsed time
        print(
            f"Fundamental frequency estimation took {elapsed_time_ms:.2f} ms")
        print("Refined frequency: ", refined)
        self.controller.selected_freq = refined
        self.refresh()

    def onclick(self, event):
        # Frequency selector functionality with axis limit check and label update
        if event.inaxes is not None and event.button == 2:

            ax = event.inaxes

            # Check if the x-coordinate is within the axis limits
            print(event.ydata)
            ylim = ax.get_ylim()
            if not (ylim[0] <= event.ydata <= ylim[1]) or event.ydata < 0:
                return  # Do not proceed if the x-coordinate is out of bounds
            self.controller.selected_freq = event.ydata
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
        self.controller.plot()
        self.refresh_widgets()
        machine_speed = self.controller.machine_speed
        selected_freq = self.controller.selected_freq
        if selected_freq:
            wavelength = 1 / selected_freq
            if self.window_type == "MD":
                frequency_in_hz = selected_freq * machine_speed / 60
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freq:.2f} 1/m ({frequency_in_hz:.2f} Hz) λ = {wavelength:.2f} m")

            elif self.window_type == "CD":
                self.selectedFrequencyLabel.setText(
                    f"Selected frequency: {selected_freq:.2f} 1/m (λ = {wavelength:.3f} m)")

        if self.paperMachineDataWindow:
            self.paperMachineDataWindow.refresh_pm_data(machine_speed)
