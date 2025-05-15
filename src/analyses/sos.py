from PyQt6.QtWidgets import QVBoxLayout
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import harmonic_fitting_units
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import numpy as np

analysis_name = "SOS Analysis"
analysis_types = ["CD"]

class AnalysisController(AnalysisControllerBase):

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "CD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.data = None
        self.fs = None
        self.selected_freqs = None
        self.channel = None

    def plot(self):
        data = self.data
        fs = self.fs
        selected_freq = self.selected_freqs[-1] if self.selected_freqs else None
        channel = self.channel

        if not selected_freq:
            self.figure.text(0.5, 0.5, "No selected frequency",
                             fontsize=14, ha='center', va='center')
            self.canvas.draw()
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
        ax.set_ylabel(f"{self.measurement.units[channel]}")
        ax.grid()

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas


class AnalysisWindow(AnalysisWindowBase[AnalysisController]):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "CD"):
        super().__init__(controller, window_type)
        self.initUI()

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
        self.refresh()

    def refresh(self):
        self.controller.updatePlot()
