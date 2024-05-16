from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHBoxLayout, QComboBox, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin
from controllers import ChannelCorrelationController

class ChannelCorrelationWindow(QWidget, DataMixin, AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin):
    def __init__(self, window_type="MD", controller: ChannelCorrelationController | None = None):
        super().__init__()
        self.window_type = window_type
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else ChannelCorrelationController(window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"{self.window_type.upper()} Channel correlation analysis ({self.dataMixin.measurement_label})")

        self.setGeometry(100, 100, 700, 950)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Channel selectors
        channelSelectorLayout = QHBoxLayout()
        self.channelSelector1 = QComboBox()
        self.channelSelector2 = QComboBox()
        for channel in self.controller.channels:
            self.channelSelector1.addItem(channel)
            self.channelSelector2.addItem(channel)
        self.channelSelector1.currentIndexChanged.connect(
            self.channelSelectionChanged)
        self.channelSelector2.currentIndexChanged.connect(
            self.channelSelectionChanged)

        channelSelectorLayout.addWidget(self.channelSelector1)
        channelSelectorLayout.addWidget(self.channelSelector2)
        mainLayout.addLayout(channelSelectorLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)
        self.addBandPassRangeSlider(mainLayout)

        # Show unfiltered data checkbox
        self.showUnfilteredCheckBox = QCheckBox("Show unfiltered data", self)
        mainLayout.addWidget(self.showUnfilteredCheckBox)
        self.showUnfilteredCheckBox.setChecked(self.controller.show_unfiltered)
        self.showUnfilteredCheckBox.stateChanged.connect(self.update_show_unfiltered)

        # Matplotlib figure and canvas
        self.plot = self.controller.plot()
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.addWidget(menuBar, 0)
        viewMenu = menuBar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def channelSelectionChanged(self, index):
        self.controller.channel1 = self.channelSelector1.currentText()
        self.controller.channel2 = self.channelSelector2.currentText()
        self.refresh()

    def update_show_unfiltered(self):
        state = self.showUnfilteredCheckBox.isChecked()
        self.controller.show_unfiltered = state
        self.refresh()

    def refresh(self):
        self.controller.plot()