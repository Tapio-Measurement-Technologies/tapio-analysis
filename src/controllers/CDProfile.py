from utils.data_loader import DataMixin
from gui.components import ExportMixin
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtCore import QObject, pyqtSignal
from utils.filters import bandpass_filter
import matplotlib.pyplot as plt
import settings
import numpy as np
import pandas as pd
import io

class CDProfileController(QObject, ExportMixin):
    updated = pyqtSignal()

    def __init__(self, window_type):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        # Matplotlib figure and canvas
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.window_type = window_type

        self.mean_profile = None
        self.selected_samples = self.dataMixin.selected_samples.copy()
        self.max_dist = np.max(self.dataMixin.cd_distances)
        self.channel = self.dataMixin.channels[0]
        self.band_pass_low = settings.CD_PROFILE_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high = settings.CD_PROFILE_BAND_PASS_HIGH_DEFAULT_1M
        self.fs = 1 / self.dataMixin.sample_step
        self.analysis_range_low = settings.CD_PROFILE_RANGE_LOW_DEFAULT * self.max_dist
        self.analysis_range_high = settings.CD_PROFILE_RANGE_HIGH_DEFAULT * self.max_dist
        self.waterfall_offset = settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT
        self.show_profiles = False
        self.show_min_max = False
        self.show_legend = False

        # Extra data
        self.extra_data = None
        self.extra_data_units = {}
        self.selected_sheet = None
        self.show_extra_data = False
        self.use_same_scale = False

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()

        if len(self.selected_samples) == 0:
            self.canvas.draw()
            return

        # Todo: These are in meters, li
        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the datamixin

        low_index = np.searchsorted(
            self.dataMixin.cd_distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.dataMixin.cd_distances, self.analysis_range_high, side='right')

        x = self.dataMixin.cd_distances[low_index:high_index]
        print(self.dataMixin.segments)

        unfiltered_data = [self.dataMixin.segments[self.channel][sample_idx]
                           [low_index:high_index] for sample_idx in self.selected_samples]

        filtered_data = [bandpass_filter(
            i, self.band_pass_low, self.band_pass_high, self.fs) for i in unfiltered_data]

        self.mean_profile = np.mean(filtered_data, axis=0)

        if self.window_type == "waterfall":
            tableau_color_cycle = plt.get_cmap('tab10')

            ax = self.figure.add_subplot(111)
            ax.set_yticks([])
            for offset, sample_idx in enumerate(self.selected_samples):
                unfiltered_data = self.dataMixin.segments[self.channel][sample_idx][low_index:high_index]
                filtered_data = bandpass_filter(
                    unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)

                y_offset = self.waterfall_offset

                color = tableau_color_cycle(sample_idx % 10)
                ax.plot(x, filtered_data - offset * y_offset, lw=1, alpha=0.9, color=color)

                # Calculate mean and add horizontal line
                mean_value = np.mean(filtered_data) - offset * y_offset
                ax.axhline(mean_value, color='gray', linestyle='-', linewidth=1)

            ax.set_title(
                f"{self.dataMixin.measurement_label} ({self.channel})")
            ax.set_xlabel("Distance [m]")
            # ax.set_ylabel("Sample Index")
            # ax.set_zlabel(
            #     f"{self.channel} [{self.dataMixin.units[self.channel]}]")

            # ax.view_init(25, -130)

        else:
            ax = self.figure.add_subplot(111)

            if self.show_profiles:
                for i in filtered_data:
                    ax.plot(x, i, alpha=0.2, color="gray")

            if self.show_min_max:
                ax.plot(x, np.min(filtered_data, axis=0),
                        alpha=0.5, color="red", label="Minimum")
                ax.plot(x, np.max(filtered_data, axis=0),
                        alpha=0.5, color="green", label="Maximum")

            ax.plot(x, self.mean_profile, label="Mean profile")
            ax.set_title(
                f"{self.dataMixin.measurement_label} ({self.channel})")

            if self.show_legend:

                handles, labels = ax.get_legend_handles_labels()
                if labels:  # This list will be non-empty if there are items to include in the legend
                    ax.legend(handles, labels, loc="upper right")

            ax.grid()

            ax.set_xlabel("Distance [m]")
            ax.set_ylabel(
                f"{self.channel} [{self.dataMixin.units[self.channel]}]")

            if self.show_extra_data and self.selected_sheet and self.extra_data is not None:
                extra_data = self.extra_data[self.selected_sheet]
                unit = self.extra_data_units[self.selected_sheet]
                extra_x = extra_data.iloc[:, 0]
                extra_y = extra_data.iloc[:, 1]
                ax2 = ax.twinx()
                ax2.plot(extra_x, extra_y, label=f"{self.selected_sheet} [{unit}]", color="green")
                ax2.set_ylabel(f"{self.selected_sheet} [{unit}]", color="tab:green")
                ax2.tick_params(axis='y', labelcolor='tab:green')

                # Also colour primary axis
                ax.set_ylabel(
                f"{self.channel} [{self.dataMixin.units[self.channel]}]", color="tab:blue")
                ax.tick_params(axis='y', labelcolor='tab:blue')

                if self.use_same_scale:
                    y1_min, y1_max = ax.get_ylim()
                    y2_min, y2_max = ax2.get_ylim()
                    combined_min = min(y1_min, y2_min)
                    combined_max = max(y1_max, y2_max)
                    ax.set_ylim(combined_min, combined_max)
                    ax2.set_ylim(combined_min, combined_max)



                if self.show_legend:
                    handles1, labels1 = ax.get_legend_handles_labels()
                    handles2, labels2 = ax2.get_legend_handles_labels()
                    handles = handles1 + handles2
                    labels = labels1 + labels2
                    ax.legend(handles, labels, loc="upper right")

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getPlotImage(self):
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png")
        return buf

    def getStatsTableData(self):
        stats = []
        mean = np.mean(self.mean_profile)
        std = np.std(self.mean_profile)
        min_val = np.min(self.mean_profile)
        max_val = np.max(self.mean_profile)
        units = self.dataMixin.units[self.channel]

        stats.append(["", f"{self.channel} [{units}]"])
        stats.append([
            "Mean:\nStdev:\nMin:\nMax:",
            f"{mean:.2f}\n{std:.2f}\n{min_val:.2f}\n{max_val:.2f}"
        ])

        return stats

    def getExportData(self):
        data = {
            "Distance [m]": self.dataMixin.cd_distances,
            f"{self.channel} [{self.dataMixin.units[self.channel]}]": self.mean_profile
        }

        return pd.DataFrame(data)
