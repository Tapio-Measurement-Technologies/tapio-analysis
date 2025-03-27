from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from qtpy.QtCore import Qt
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin, ShowProfilesMixin, ShowLegendMixin, ShowConfidenceIntervalMixin, ShowMinMaxMixin, WaterfallOffsetMixin, ExtraDataMixin, CopyPlotMixin, ChildWindowCloseMixin
from controllers import CDProfileController
from matplotlib.ticker import AutoMinorLocator
import settings


class CDProfileWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin, ShowProfilesMixin, ShowLegendMixin, ShowConfidenceIntervalMixin, ShowMinMaxMixin, WaterfallOffsetMixin, ExtraDataMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="waterfall", controller: CDProfileController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else CDProfileController(
            window_type)
        self.window_type = window_type
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)

        fileMenu = menuBar.addMenu('File')
        exportAction = self.controller.initExportAction(
            self, "Export mean profile")
        fileMenu.addAction(exportAction)

        if not self.window_type == "waterfall":
            loadExtraDataAction = QAction('Load extra data', self)
            loadExtraDataAction.setShortcut("Ctrl+O")
            fileMenu.addAction(loadExtraDataAction)
            loadExtraDataAction.triggered.connect(self.loadExtraData)

        viewMenu = menuBar.addMenu('View')

        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"CD Profile ({self.dataMixin.measurement_label})")
        self.setGeometry(*settings.CD_PROFILE_WINDOW_GEOMETRY)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)
        # Add the channel selector
        self.addChannelSelector(mainLayout)

        if not self.window_type == "waterfall":
            # Extra data controls, hidden until extra data is loaded
            self.addExtraDataWidget(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)

        if not self.window_type == "waterfall":
            self.addShowProfilesCheckbox(mainLayout)
            self.addShowConfidenceIntervalCheckbox(
                mainLayout, settings.CD_PROFILE_CONFIDENCE_INTERVAL)
            self.addShowMinMaxCheckbox(mainLayout)
            self.addShowLegendCheckbox(mainLayout)
        else:
            self.addWaterfallOffsetSlider(mainLayout)

        # Add statistics labels
        statsLayout = QVBoxLayout()  # Separate layout for statistics labels
        self.meanLabel = QLabel("Mean: ")
        self.stdLabel = QLabel("σ: ")
        self.minLabel = QLabel("Min: ")
        self.maxLabel = QLabel("Max: ")
        self.rangeLabel = QLabel("Range: ")

        for label in [self.meanLabel, self.stdLabel, self.minLabel, self.maxLabel, self.rangeLabel]:
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            statsLayout.addWidget(label)

        mainLayout.addLayout(statsLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        if not self.window_type == "waterfall":
            self.initShowLegendCheckbox(block_signals=True)
            self.initShowConfidenceIntervalCheckbox(block_signals=True)
            self.initShowMinMaxCheckbox(block_signals=True)
            self.initShowProfilesCheckbox(block_signals=True)

    def refresh(self):
        # logging.info("Refresh")
        self.controller.updatePlot()
        self.refresh_widgets()

        self.updateStatistics(self.controller.mean_profile)
