from utils.data_loader import DataMixin
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtCore import QObject, pyqtSignal
from matplotlib import pyplot as plt
from scipy.optimize import curve_fit
import settings
import numpy as np
import io

class FormationController(QObject):
    updated = pyqtSignal()

    def __init__(self, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        # Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.window_type = window_type

        if self.window_type == "MD":
            self.max_dist = np.max(self.dataMixin.distances)
            self.distances = self.dataMixin.distances
            self.analysis_range_low = settings.MD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist
            self.analysis_range_high = settings.MD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist

        elif self.window_type == "CD":
            self.max_dist = np.max(self.dataMixin.cd_distances)
            self.distances = self.dataMixin.cd_distances
            self.analysis_range_low = settings.CD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist
            self.analysis_range_high = settings.CD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist

            self.selected_samples = self.dataMixin.selected_samples.copy()
            self.sampleSelectorWindow = None

        self.channel = self.dataMixin.channels[1]
        self.transmission_channel = settings.FORMATION_TRANSMISSION_CHANNEL
        self.bw_channel = settings.FORMATION_BW_CHANNEL
        self.show_profiles = False

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Todo: These are in meters, li
        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the datamixin
        if self.window_type == "MD":

            low_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_high, side='right')

            x = self.dataMixin.distances[low_index:high_index]
            unfiltered_data = self.dataMixin.channel_df[self.channel][low_index:high_index]

            transmission_data = self.dataMixin.channel_df[self.transmission_channel][low_index:high_index]

            bw_data = self.dataMixin.channel_df[self.bw_channel][low_index:high_index]

            def linear(x, a, b):
                return a * x + b
            params, covariance = curve_fit(
                linear, transmission_data, bw_data)

            def f(x):
                return linear(x, *params)

            vectorized_function = np.vectorize(f)
            estimated_bw = vectorized_function(transmission_data)

            correlation_matrix = np.corrcoef(bw_data, estimated_bw)
            self.correlation_coefficient = correlation_matrix[0, 1]
            print("Correlation Coefficient:", self.correlation_coefficient)

            y = self.calculate_formation_index(estimated_bw)

        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_high, side='right')

            x = self.dataMixin.cd_distances[low_index:high_index]

            transmission_data = [self.dataMixin.segments[self.transmission_channel]
                                 [sample_idx][low_index:high_index] for sample_idx in self.selected_samples]

            transmission_mean_profile = np.mean(transmission_data, axis=0)
            bw_mean_profile = np.mean([self.dataMixin.segments[self.bw_channel][sample_idx]
                                       [low_index:high_index] for sample_idx in self.selected_samples], axis=0)

            def linear(x, a, b):
                return a * x + b
            params, covariance = curve_fit(
                linear, transmission_mean_profile, bw_mean_profile)

            def f(x):
                return linear(x, *params)

            vectorized_function = np.vectorize(f)
            estimated_bw_profiles = [
                vectorized_function(i) for i in transmission_data]

            correlation_matrix = np.corrcoef(
                bw_mean_profile, np.mean(estimated_bw_profiles, axis=0))
            self.correlation_coefficient = correlation_matrix[0, 1]
            print("Correlation Coefficient:", self.correlation_coefficient)
            formation_profiles = [self.calculate_formation_index(estimated_bw)
                                  for estimated_bw in estimated_bw_profiles]

            y = np.mean(formation_profiles, axis=0)

            if self.show_profiles:
                for i in formation_profiles:
                    ax.plot(x[399:], i, color="gray", alpha=0.5, lw=0.5)

        x = x[399:]

        show_unfiltered = True
        ax.plot(x, y)
        ax.set_title(
            f"{self.dataMixin.measurement_label} - Formation index ({self.channel})")

        ax.set_xlabel("Distance [m]")
        params = {'mathtext.default': 'regular'}
        plt.rcParams.update(params)
        ax.set_ylabel(f"$f_N$")
        ax.grid()
        self.stats = y

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getPlotImage(self):
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png")
        return buf

    def getStatsTableData(self):
        stats = []
        mean = np.mean(self.stats)
        std = np.std(self.stats)
        min_val = np.min(self.stats)
        max_val = np.max(self.stats)
        units = self.dataMixin.units[self.channel]

        stats.append(["", f"{self.channel} [{units}]"])
        stats.append(["Mean:", f"{mean:.2f}"])
        stats.append(["Stdev:", f"{std:.2f}"])
        stats.append(["Min:", f"{min_val:.2f}"])
        stats.append(["Max:", f"{max_val:.2f}"])
        stats.append(["", ""])
        stats.append(["Correlation coefficient:", f"{self.correlation_coefficient:.2f}"])

        return stats

    def calculate_formation_index(self, arr, window_size=400):
        arr = np.array(arr)
        num_values = len(arr) - window_size + 1
        result = np.empty(num_values)

        for i in range(num_values):
            window = arr[i:i + window_size]
            variance = np.var(window)
            sqrt_mean = np.sqrt(np.mean(window))
            result[i] = variance / sqrt_mean if sqrt_mean != 0 else 0

        return result