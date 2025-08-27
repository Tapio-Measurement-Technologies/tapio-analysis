from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import harmonic_fitting_units
import numpy as np

analysis_name = "SOS Analysis"
analysis_types = ["MD"]

class AnalysisController(AnalysisControllerBase):
    selected_freqs: list[float]

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.data = None

        self.set_default('selected_freqs', None)
        self.set_default('channel', None)
        self.set_default('radius_offset_ratio', 0.5)
        self.set_default('radius_max_multiplier', 1.1)

    def plot(self):
        data = self.data
        fs = self.fs
        selected_freq = self.selected_freqs[-1] if self.selected_freqs else None
        channel = self.channel

        if not selected_freq:
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.axis('off')
            ax.text(0.5, 0.5, "No selected frequency",
                    fontsize=14, ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            return self.canvas

        self.figure.clear()

        ax = self.figure.add_subplot(111, projection='polar')
        y = harmonic_fitting_units(data, fs, selected_freq)

        # Convert distance to angles (theta) for polar plot
        theta = np.linspace(0, 2*np.pi, len(y), endpoint=False)

        # Append first point to end to close the polar plot
        y = np.append(y, y[0])
        theta = np.append(theta, theta[0])

        # Add configurable offset to radius so center is empty
        radius_offset = self.radius_offset_ratio * np.max(np.abs(y)) if np.max(np.abs(y)) > 0 else 0.1
        r = np.abs(y) + radius_offset

        ax.plot(theta, r)

        ax.set_title(f"{channel} pattern at {selected_freq:.2f} 1/m")
        ax.set_ylim(0, np.max(r) * self.radius_max_multiplier)
        ax.set_rorigin(-np.max(r) * self.radius_offset_ratio)  # Move the origin down to create space
        ax.grid(True, alpha=0.3)
        ax.set_rticks(np.linspace(radius_offset, np.max(r), 3))  # Radial grid lines
        ax.set_thetagrids(np.arange(0, 360, 30))  # Angular grid lines every 30 degrees

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas


class AnalysisWindow(AnalysisWindowBase[AnalysisController]):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.initUI()

    def initUI(self):
        self.setWindowTitle("SOS analysis")
        self.setGeometry(100, 100, 800, 600)

        # Matplotlib figure and canvas
        self.controller.addPlot(self.main_layout)

        self.refresh()

    def refresh(self):
        self.controller.updatePlot()
