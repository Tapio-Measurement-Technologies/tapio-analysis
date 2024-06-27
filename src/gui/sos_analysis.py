from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from controllers import SOSAnalysisController, SpectrumController

class SOSAnalysisWindow(QWidget):

    closed = pyqtSignal()

    def __init__(self, spectrumController: SpectrumController):
        super().__init__()
        self.spectrumController = spectrumController
        self.controller = SOSAnalysisController(self.spectrumController)
        self.initUI()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def initUI(self):
        self.setWindowTitle("SOS analysis")
        self.setGeometry(100, 100, 500, 300)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)

        # Optional: Adding Matplotlib Navigation Toolbar
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

    def refresh(self):
        self.controller.updatePlot()
