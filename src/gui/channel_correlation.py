from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin, ShowUnfilteredMixin, DoubleChannelMixin, CopyPlotMixin, ChildWindowCloseMixin
from controllers import ChannelCorrelationController


class ChannelCorrelationWindow(QWidget, DataMixin, AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin, ShowUnfilteredMixin, DoubleChannelMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="MD", controller: ChannelCorrelationController | None = None):
        super().__init__()
        self.window_type = window_type
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else ChannelCorrelationController(
            window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"{self.window_type.upper()} Channel correlation analysis ({
                            self.dataMixin.measurement_label})")

        self.setGeometry(100, 100, 700, 950)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Channel selectors
        self.addChannelSelectors(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)
        self.addBandPassRangeSlider(mainLayout)

        # Show unfiltered data checkbox
        self.addShowUnfilteredCheckbox(mainLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        viewMenu = menuBar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initShowUnfilteredCheckbox(block_signals=True)
        self.initChannelSelectors(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
