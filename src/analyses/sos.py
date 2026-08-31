from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import harmonic_fitting_units
import numpy as np
import settings

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

        if len(y) == 0:
            ax.axis('off')
            ax.text(0.5, 0.5, "Not enough data for the selected frequency",
                    fontsize=12, ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            self.updated.emit()
            return self.canvas

        # harmonic_fitting_units returns exactly one revolution on an even
        # angular grid, so theta maps directly onto it.
        theta = np.linspace(0, 2*np.pi, len(y), endpoint=False)

        # Append first point to end to close the polar plot
        y = np.append(y, y[0])
        theta = np.append(theta, theta[0])

        # The fitted revolution is mean free and signed. Shift it outwards by a
        # constant so every radius is positive, rather than taking the absolute
        # value - abs() folds troughs onto peaks and draws a single high spot on
        # a roll as two opposed high spots.
        peak = float(np.max(np.abs(y)))
        if peak > 0:
            radius_offset = peak / max(self.radius_offset_ratio, 1e-9)
        else:
            radius_offset = 0.1
        r = y + radius_offset

        ax.plot(theta, r)

        units = self.measurement.units.get(channel, "") if channel else ""
        ax.set_title(f"{channel} pattern at {selected_freq:.2f} 1/m")
        r_max = float(np.max(r))
        ax.set_ylim(0, r_max * self.radius_max_multiplier)
        ax.set_rorigin(-r_max * self.radius_offset_ratio)  # Move the origin down to create space
        ax.grid(True, alpha=0.3)
        # Label the radial ticks with the signed deviation they represent, so the
        # constant offset used to keep the radius positive is not read as signal.
        rticks = np.linspace(radius_offset - peak, radius_offset + peak, 3)
        ax.set_rticks(rticks)
        ax.set_yticklabels(
            [f"{tick - radius_offset:+.3g}{(' ' + units) if units else ''}" for tick in rticks])
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
        self.resize(*settings.SOS_ANALYSIS_WINDOW_SIZE)

        # Matplotlib figure and canvas
        self.controller.addPlot(self.main_layout)

        self.refresh()

    def refresh(self):
        self.controller.updatePlot()
