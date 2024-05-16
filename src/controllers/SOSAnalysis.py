from utils.data_loader import DataMixin
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtCore import QObject, pyqtSignal
from utils.signal_processing import harmonic_fitting_units
import numpy as np
import io

class SOSAnalysisController(QObject):
    updated = pyqtSignal()

    def __init__(self, spectrumController):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.spectrumController = spectrumController
        # Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

    def plot(self):
        data = self.spectrumController.data
        fs = self.spectrumController.fs
        selected_freq = self.spectrumController.selected_freq
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

    def getPlotImage(self):
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png")
        return buf