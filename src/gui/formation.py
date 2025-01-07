from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from qtpy.QtCore import Qt
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, StatsMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin
from controllers import FormationController


class FormationWindow(QWidget, DataMixin, AnalysisRangeMixin, StatsMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin):
    def __init__(self, window_type="MD", controller: FormationController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else FormationController(window_type)
        self.window_type = window_type
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        viewMenu = menuBar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"Formation analysis ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Add the channel selector
        # self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        if self.window_type =="CD":
            self.addShowProfilesCheckbox(mainLayout)


        statsLayout = QVBoxLayout()  # Separate layout for statistics labels

        self.textLabel = QLabel(
            "Formation index (calculated from transmission correlated to BW)")
        self.correlationLabel = QLabel("Correlation coefficient: ")
        self.meanLabel = QLabel("Mean: ")
        self.stdLabel = QLabel("σ: ")
        self.minLabel = QLabel("Min: ")
        self.maxLabel = QLabel("Max: ")

        for label in [self.textLabel, self.correlationLabel, self.meanLabel, self.stdLabel, self.minLabel, self.maxLabel]:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            statsLayout.addWidget(label)

        mainLayout.addLayout(statsLayout)

        # self.addBandPassRangeSlider(mainLayout)

        # Now add a stretch factor before adding the figure canvas to give it priority to expand
        # mainLayout.addStretch(1)

        self.plot = self.controller.getCanvas()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        if self.window_type == "CD":
            self.initShowProfilesCheckbox(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.correlationLabel.setText(f"Correlation coefficient: {self.controller.correlation_coefficient:.2f}")
        self.updateStatistics(self.controller.stats, show_units=False)
