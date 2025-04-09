from utils.data_loader import DataMixin
from gui.components import PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox
from matplotlib import pyplot as plt
from scipy.optimize import curve_fit
import settings
import numpy as np


class FormationController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.window_type = window_type
        self.warning_message = None
        self.can_calculate = self.check_required_channels()

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

        self.show_profiles = False

    def check_required_channels(self):
        """Check if all required channels exist and show alert if not."""
        required_channels = {
            'BW': settings.FORMATION_BW_CHANNEL,
            'Transmission': settings.FORMATION_TRANSMISSION_CHANNEL
        }
        
        missing_channels = []
        for channel_type, channel_name in required_channels.items():
            if channel_name not in self.dataMixin.channels:
                missing_channels.append(f"{channel_type} ({channel_name})")
        
        if missing_channels:
            self.warning_message = f"Required channels not found: {', '.join(missing_channels)}"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("Formation Index Calculation Not Available")
            msg.setInformativeText(self.warning_message)
            msg.setWindowTitle("Missing Channels")
            msg.exec()
            return False
            
        self.channel = settings.FORMATION_BW_CHANNEL
        self.transmission_channel = settings.FORMATION_TRANSMISSION_CHANNEL
        self.bw_channel = settings.FORMATION_BW_CHANNEL
        return True

    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if not self.can_calculate:
            self.figure.text(0.5, 0.5, "Formation Index calculation not available\nRequired channels missing",
                           ha='center', va='center', color='red')
            self.canvas.draw()
            self.stats = None  # Clear any previous stats
            return self.canvas

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
                    ax.plot(x[settings.FORMATION_WINDOW_SIZE-1:],
                            i, color="gray", alpha=0.5, lw=0.5)

        x = x[settings.FORMATION_WINDOW_SIZE-1:]

        show_unfiltered_data = True
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

    def getStatsTableData(self):
        stats = []
        mean = np.mean(self.stats)
        std = np.std(self.stats)
        min_val = np.min(self.stats)
        max_val = np.max(self.stats)
        units = self.dataMixin.units[self.channel]

        stats.append(["Correlation coefficient:",
                     f"{self.correlation_coefficient:.2f}"])
        stats.append(["", f"{self.channel} [{units}]"])
        stats.append([
            "Mean:\nStdev:\nMin:\nMax:",
            f"{mean:.2f}\n{std:.2f}\n{min_val:.2f}\n{max_val:.2f}"
        ])

        return stats

    def calculate_formation_index(self, arr, window_size=settings.FORMATION_WINDOW_SIZE):
        arr = np.array(arr)
        num_values = len(arr) - window_size + 1
        result = np.empty(num_values)

        for i in range(num_values):
            window = arr[i:i + window_size]
            variance = np.var(window)
            sqrt_mean = np.sqrt(np.mean(window))
            result[i] = variance / sqrt_mean if sqrt_mean != 0 else 0

        return result
