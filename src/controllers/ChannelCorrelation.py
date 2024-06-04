from utils.data_loader import DataMixin
from gui.components import PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
from utils.filters import bandpass_filter
from scipy.stats import pearsonr
import settings
import numpy as np

class ChannelCorrelationController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.window_type = window_type

        if self.window_type == "MD":
            self.max_dist = np.max(self.dataMixin.distances)
            self.distances = self.dataMixin.distances
        elif self.window_type == "CD":
            self.max_dist = np.max(self.dataMixin.cd_distances)
            self.distances = self.dataMixin.cd_distances

        channel_correlation_config = {
            "MD": {
                "band_pass_low": settings.MD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.MD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT,
            },
            "CD": {
                "band_pass_low": settings.CD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.CD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT,
            }
        }

        self.show_unfiltered_data = False
        self.selected_samples = self.dataMixin.selected_samples.copy()
        self.channels = self.dataMixin.channels
        self.channel1 = self.channels[0]
        self.channel2 = self.channels[0]
        config = channel_correlation_config[self.window_type]
        self.band_pass_low = config["band_pass_low"]
        self.band_pass_high = config["band_pass_high"]
        self.fs = 1 / self.dataMixin.sample_step
        self.analysis_range_low = config["analysis_range_low"] * self.max_dist
        self.analysis_range_high = config["analysis_range_high"] * \
            self.max_dist

    def plot(self):
        self.figure.clear()
        ax_correlation = self.figure.add_subplot(211)

        ax1 = self.figure.add_subplot(212)

        # Plot for the first channel
        data1 = self.plotChannelData(ax1, self.channel1, 'tab:blue')

        # Adding a second Y axis for the second channel
        ax2 = ax1.twinx()
        data2 = self.plotChannelData(ax2, self.channel2, 'tab:green')

        corr_coeff, _ = pearsonr(data1, data2)
        ax_correlation.scatter(data1, data2, s=1)
        ax_correlation.set_title(f"Correlation coefficient: {corr_coeff:.2f}")
        ax_correlation.set_xlabel(
            f"{self.channel1} [{self.dataMixin.units[self.channel1]}]")
        ax_correlation.set_ylabel(
            f"{self.channel2} [{self.dataMixin.units[self.channel2]}]")
        ax_correlation.grid()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def plotChannelData(self, ax, channel, color):
        # This function needs to be adapted to how your data is structured and how you filter/prepare it
        if self.window_type == "MD":
            low_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_high, side='right')

            x = self.dataMixin.distances[low_index:high_index]
            unfiltered_data = self.dataMixin.channel_df[channel][low_index:high_index]
            filtered_data = bandpass_filter(
                unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)
        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_high, side='right')

            x = self.dataMixin.cd_distances[low_index:high_index]

            unfiltered_data = np.mean([self.dataMixin.segments[channel][sample_idx][low_index:high_index] for sample_idx in self.selected_samples], axis=0)

            filtered_data = bandpass_filter(
                unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)

        if self.show_unfiltered_data:
            ax.plot(x, unfiltered_data, alpha=0.5, color="gray")
        ax.plot(x, filtered_data, color=color, alpha=0.9)
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(
            f"{channel} [{self.dataMixin.units[channel]}]", color=color)
        ax.tick_params(axis='y', labelcolor=color)
        # ax.grid()

        return filtered_data

    def getStatsTableData(self):
        stats = []
        return stats