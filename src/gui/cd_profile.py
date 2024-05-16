from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from qtpy.QtCore import Qt
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin
from controllers import CDProfileController

class CDProfileWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin):
    def __init__(self, window_type="waterfall", controller: CDProfileController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else CDProfileController(window_type)
        self.window_type = window_type
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.addWidget(menuBar, 0)

        fileMenu = menuBar.addMenu('File')
        exportAction = self.controller.initExportAction(self, "Export mean profile")
        fileMenu.addAction(exportAction)

        viewMenu = menuBar.addMenu('View')

        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"CD Profile ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)
        # Add the channel selector
        self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)

        # self.showUnfilteredCheckBox = QCheckBox("Show unfiltered data", self)
        # mainLayout.addWidget(self.showUnfilteredCheckBox)
        # self.showUnfilteredCheckBox.setChecked(False)
        # self.showUnfilteredCheckBox.stateChanged.connect(self.refresh)

        if not self.window_type == "waterfall":
            self.showProfilesCheckBox = QCheckBox(
                "Show individual profes", self)
            mainLayout.addWidget(self.showProfilesCheckBox)
            self.showProfilesCheckBox.setChecked(self.controller.show_profiles)
            self.showProfilesCheckBox.stateChanged.connect(self.update_show_profiles)

            self.showMinMaxCheckBox = QCheckBox("Show min/max", self)
            mainLayout.addWidget(self.showMinMaxCheckBox)
            self.showMinMaxCheckBox.setChecked(self.controller.show_min_max)
            self.showMinMaxCheckBox.stateChanged.connect(self.update_show_min_max)

            self.showLegendCheckBox = QCheckBox("Show legend", self)
            mainLayout.addWidget(self.showLegendCheckBox)
            self.showLegendCheckBox.setChecked(self.controller.show_legend)
            self.showLegendCheckBox.stateChanged.connect(self.update_show_legend)

        # Add statistics labels
        statsLayout = QVBoxLayout()  # Separate layout for statistics labels
        self.meanLabel = QLabel("Mean: ")
        self.stdLabel = QLabel("σ: ")
        self.minLabel = QLabel("Min: ")
        self.maxLabel = QLabel("Max: ")

        for label in [self.meanLabel, self.stdLabel, self.minLabel, self.maxLabel]:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            statsLayout.addWidget(label)

        mainLayout.addLayout(statsLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.plot()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh(self):
        # logging.info("Refresh")
        self.controller.plot()
        self.updateStatistics(self.controller.mean_profile)

    def update_show_profiles(self):
        state = self.showProfilesCheckBox.isChecked()
        self.controller.show_profiles = state
        self.refresh()

    def update_show_min_max(self):
        state = self.showMinMaxCheckBox.isChecked()
        self.controller.show_min_max = state
        self.refresh()

    def update_show_legend(self):
        state = self.showLegendCheckBox.isChecked()
        self.controller.show_legend = state
        self.refresh()