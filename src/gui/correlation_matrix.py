from PyQt6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, BandPassFilterMixin
from controllers import CorrelationMatrixController

class CorrelationMatrixWindow(QWidget, DataMixin, AnalysisRangeMixin, BandPassFilterMixin):

    def __init__(self, window_type="MD", controller: CorrelationMatrixController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else CorrelationMatrixController(window_type)
        self.window_type = window_type
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"Correlation matrix ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 750, 750)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)
        self.plot = self.controller.plot()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh(self):
        self.controller.plot()
