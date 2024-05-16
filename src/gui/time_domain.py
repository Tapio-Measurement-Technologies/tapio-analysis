from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QMenuBar
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from qtpy.QtCore import Qt

from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, StatsMixin
from controllers import TimeDomainController

class TimeDomainWindow(QWidget, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, StatsMixin):
    def __init__(self, controller: TimeDomainController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else TimeDomainController()
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()

        layout.addWidget(menuBar, 0)

        fileMenu = menuBar.addMenu('File')

        exportAction = self.controller.initExportAction(self, "Export current data")
        fileMenu.addAction(exportAction)

    def initUI(self):
        self.setWindowTitle(
            f"Time domain analysis ({self.controller.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()

        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)

        # Add the channel selector
        self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)

        self.showUnfilteredCheckBox = QCheckBox("Show unfiltered data", self)
        mainLayout.addWidget(self.showUnfilteredCheckBox)
        show_unfiltered_data = self.controller.show_unfiltered_data
        self.showUnfilteredCheckBox.setChecked(show_unfiltered_data)
        self.showUnfilteredCheckBox.stateChanged.connect(self.update_show_unfiltered)

        # Add statistics labels
        statsLayout = QVBoxLayout()  # Separate layout for statistics labels
        statsLayout = QVBoxLayout()  # Use a vertical layout for statistics labels
        self.meanLabel = QLabel("Mean: ")
        self.stdLabel = QLabel("σ: ")
        self.minLabel = QLabel("Min: ")
        self.maxLabel = QLabel("Max: ")

        for label in [self.meanLabel, self.stdLabel, self.minLabel, self.maxLabel]:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            statsLayout.addWidget(label)
        # Add the stats layout to the main layout
        mainLayout.addLayout(statsLayout)

        # Now add a stretch factor before adding the figure canvas to give it priority to expand
        # mainLayout.addStretch(1)

        # Matplotlib figure and canvas
        self.plot = self.controller.plot()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh(self):
        self.controller.plot()
        self.updateStatistics(self.controller.data)

    def update_show_unfiltered(self):
        state = self.showUnfilteredCheckBox.isChecked()
        self.controller.show_unfiltered_data = state
        self.refresh()
