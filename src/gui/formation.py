from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from qtpy.QtCore import Qt
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin, ChildWindowCloseMixin, StatsWidget
from controllers import FormationController
import settings


class FormationWindow(QWidget, DataMixin, AnalysisRangeMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="MD", controller: FormationController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()


        self.controller = controller if controller else FormationController(
            window_type)
        if not self.controller.can_calculate:
            self.close()
            return
        self.window_type = window_type
        self.sampleSelectorWindow = None
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
        if settings.FORMATION_TITLE_SHOW:
            self.setWindowTitle(
                f"Formation analysis ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        if self.window_type == "CD":
            self.addShowProfilesCheckbox(mainLayout)

        # Add description label
        self.textLabel = QLabel(
            f"Formation index (calculated from {settings.FORMATION_TRANSMISSION_CHANNEL} correlated to {settings.FORMATION_BW_CHANNEL})")
        self.textLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        mainLayout.addWidget(self.textLabel)

        # Add correlation coefficient label
        self.correlationLabel = QLabel("Correlation coefficient: ")
        self.correlationLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        mainLayout.addWidget(self.correlationLabel)

        # Add statistics widget
        self.stats_widget = StatsWidget()
        mainLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
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
        self.correlationLabel.setText(
            f"Correlation coefficient: {self.controller.correlation_coefficient:.2f}")
        self.stats_widget.update_statistics(self.controller.stats, "")
