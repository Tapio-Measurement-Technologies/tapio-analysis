from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QPushButton
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from gui.components import AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin, SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin, CopyPlotMixin, AutoDetectPeaksMixin, ChildWindowCloseMixin
from utils.data_loader import DataMixin
from gui.paper_machine_data import PaperMachineDataWindow
from gui.sos_analysis import SOSAnalysisWindow
from utils.signal_processing import hs_units
from controllers import CepstrumController 
import settings


class CepstrumWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, FrequencyRangeMixin, MachineSpeedMixin,
                     SampleSelectMixin, SpectrumLengthMixin, ShowWavelengthMixin, CopyPlotMixin, AutoDetectPeaksMixin,
                     ChildWindowCloseMixin):

    def __init__(self, window_type="MD", controller: CepstrumController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.window_type = window_type
        self.controller = controller if controller else CepstrumController(
            window_type)
        self.paperMachineDataWindow = None
        self.sosAnalysisWindow = None
        self.sampleSelectorWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        fileMenu = menuBar.addMenu('File')
        exportAction = self.controller.initExportAction(
            self, "Export spectrum")
        fileMenu.addAction(exportAction)

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
                self.updateElements, self.window_type, self.checked_elements)
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

    def initUI(self):

        self.setWindowTitle(f"{self.window_type} Spectral analysis ({
                            self.dataMixin.measurement_label})")
        self.setGeometry(*settings.SPECTRUM_WINDOW_GEOMETRY)

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

        # self.frequencyRangeSlider.setValue((self.frequency_range_low, self.frequency_range_high))

        if self.window_type == "MD":
            self.addShowWavelengthCheckbox(mainLayout)

        if settings.SPECTRUM_AUTO_DETECT_PEAKS:
            self.addAutoDetectPeaksCheckbox(mainLayout)

        self.selectedFrequencyLabel = QLabel("Selected frequency: None")
        mainLayout.addWidget(self.selectedFrequencyLabel)

        self.refineButton = QPushButton("Refine")
        self.refineButton.clicked.connect(self.refineFrequency)
        mainLayout.addWidget(self.refineButton)

        self.clearButton = QPushButton("Clear")
        self.clearButton.clicked.connect(self.clearFrequency)
        mainLayout.addWidget(self.clearButton)

        self.plot = self.controller.getCanvas()

        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.plot.mpl_connect('button_press_event', self.onclick)

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
        d = self.dataMixin.channel_df[self.controller.channel][self.controller.low_index:self.controller.high_index]
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
