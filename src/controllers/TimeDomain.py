from utils.data_loader import DataMixin
from gui.components import ExportMixin, PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
from utils.filters import bandpass_filter
import settings
import numpy as np
import pandas as pd

class TimeDomainController(QObject, PlotMixin, ExportMixin):
    updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()

        self.max_dist = np.max(self.dataMixin.distances)
        self.fs = 1 / self.dataMixin.sample_step

        self.analysis_range_low   = settings.TIME_DOMAIN_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist
        self.analysis_range_high  = settings.TIME_DOMAIN_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist
        self.band_pass_low        = settings.TIME_DOMAIN_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high       = settings.TIME_DOMAIN_BAND_PASS_HIGH_DEFAULT_1M
        self.channel              = self.dataMixin.channels[0]
        self.show_unfiltered_data = False

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Todo: These are in meters, li
        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the datamixin

        low_index = np.searchsorted(
            self.dataMixin.distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.dataMixin.distances, self.analysis_range_high, side='right')

        self.distances = self.dataMixin.distances[low_index:high_index]
        unfiltered_data = self.dataMixin.channel_df[self.channel][low_index:high_index]
        self.data = bandpass_filter(
            unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)

        if self.show_unfiltered_data:
            ax.plot(self.distances, unfiltered_data, alpha=0.5, color="gray")
        ax.plot(self.distances, self.data)
        ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel})")
        ax.grid()

        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"{self.channel} [{self.dataMixin.units[self.channel]}]")

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        mean = np.mean(self.data)
        std = np.std(self.data)
        min_val = np.min(self.data)
        max_val = np.max(self.data)
        units = self.dataMixin.units[self.channel]

        stats.append(["", f"{self.channel} [{units}]"])
        stats.append([
            "Mean:\nStdev:\nMin:\nMax:",
            f"{mean:.2f}\n{std:.2f}\n{min_val:.2f}\n{max_val:.2f}"
        ])

        return stats

    def getExportData(self):
        data = {
            "Distance [m]": self.distances,
            f"{self.channel} [{self.dataMixin.units[self.channel]}]": self.data
        }

        return pd.DataFrame(data)