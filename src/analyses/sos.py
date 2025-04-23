from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import QObject, pyqtSignal
from utils.data_loader import DataMixin
from utils.signal_processing import harmonic_fitting_units
from gui.components import PlotMixin
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np
from utils.types import AnalysisType

analysis_name = "SOS Analysis"
analysis_types = [AnalysisType.CD]

class AnalysisController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, spectrumController):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.spectrumController = spectrumController

    def plot(self):
        data = self.spectrumController.data
        fs = self.spectrumController.fs
        selected_freq = self.spectrumController.selected_freqs[-1] if self.spectrumController.selected_freqs else None
        channel = self.spectrumController.channel

        if not selected_freq:
            return self.canvas

        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Example plotting code
        # You would replace the x and y with your actual data
        y = harmonic_fitting_units(data, fs, selected_freq)
        distance = np.linspace(0, 1/selected_freq, len(y))

        ax.plot(distance, y)
        ax.set_title(f"{channel} variation at {selected_freq:.2f} 1/m")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"{self.dataMixin.units[channel]}")
        ax.grid()

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas


class AnalysisWindow(QWidget):

    closed = pyqtSignal()

    def __init__(self, spectrumController):
        super().__init__()
        self.spectrumController = spectrumController
        self.controller = AnalysisController(self.spectrumController)
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
