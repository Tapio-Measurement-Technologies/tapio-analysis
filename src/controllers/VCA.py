from utils.data_loader import DataMixin
from gui.components import PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
from utils.filters import bandpass_filter
import settings
import numpy as np
from matplotlib.ticker import MaxNLocator
from matplotlib import colors, cm

class VCAController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()

        self.selected_samples = self.dataMixin.selected_samples.copy()
        self.max_dist = np.max(self.dataMixin.cd_distances)
        self.channel = self.dataMixin.channels[0]
        self.band_pass_low = settings.VCA_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high = settings.VCA_BAND_PASS_HIGH_DEFAULT_1M
        self.analysis_range_low = settings.VCA_RANGE_LOW_DEFAULT * self.max_dist
        self.analysis_range_high = settings.VCA_RANGE_HIGH_DEFAULT * self.max_dist
        self.fs = 1 / self.dataMixin.sample_step

    def plot(self):
        self.figure.clear()

        if len(self.selected_samples) == 0:
            self.canvas.draw()
            return

        # Calculate indices for slicing based on the analysis range
        low_index = np.searchsorted(
            self.dataMixin.cd_distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.dataMixin.cd_distances, self.analysis_range_high, side='right')

        # Preparation of data for plotting
        self.filtered_data = [bandpass_filter(
            self.dataMixin.segments[self.channel][sample_idx][low_index:high_index],
            self.band_pass_low, self.band_pass_high, self.fs) for sample_idx in self.selected_samples]

        # Calculate the mean profile and residuals
        mean_profile = np.mean(self.filtered_data, axis=0)
        residuals, residual_variance = self.calculate_residuals_and_variance(
            np.array(self.filtered_data), 0, 0)

        # Setup the grid and axes
        gs = self.figure.add_gridspec(
            4, 3, width_ratios=[2, 16, 1], height_ratios=[2, 5, 5, 2], wspace=0.1, hspace=0.5)
        md_mean_ax = self.figure.add_subplot(gs[1, 0])
        cd_profile_ax = self.figure.add_subplot(gs[0, 1])
        cd_profile_ax.margins(x=0)
        ax2 = self.figure.add_subplot(gs[1, 1])
        ax2.yaxis.set_major_locator(MaxNLocator(integer=True))

        ax4 = self.figure.add_subplot(gs[2, 1])  # For the residual heatmap
        ax4.yaxis.set_major_locator(MaxNLocator(integer=True))

        residual_profile_ax = self.figure.add_subplot(
            gs[3, 1])  # For the residual profile

        data_colorbar_ax = self.figure.add_subplot(gs[1, 2])
        residual_colorbar_ax = self.figure.add_subplot(gs[2, 2])

        # Common settings for the colormap
        cmap = cm.get_cmap(settings.VCA_COLORMAP)
        norm = colors.Normalize(vmin=mean_profile.min(),
                                vmax=mean_profile.max())

        x_data = self.dataMixin.cd_distances[low_index:high_index]
        xmin, xmax = x_data[0], x_data[-1]
        ymin, ymax = 0, len(self.filtered_data)

        # Plotting the MD mean profile
        md_mean = np.mean(self.filtered_data, axis=1)
        md_mean_ax.plot(md_mean, range(1, 1+len(md_mean)),
                        color='tab:blue', linewidth=2)

        md_mean_ax.set(
            xlabel=f"MD mean [{self.dataMixin.units[self.channel]}]", ylabel="Sample index")
        md_mean_ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        md_mean_ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        md_mean_ax.grid()

        md_mean_ax.margins(y=0)

        # Plotting the CD profile on top
        cd_profile_ax.plot(x_data, mean_profile)
        cd_profile_ax.set(
            xlabel="Distance [m]", ylabel=f"CD mean [{self.dataMixin.units[self.channel]}]")
        cd_profile_ax.grid()

        # Plotting the main heatmap
        cax = ax2.imshow(self.filtered_data, aspect='auto', origin='lower',
                         cmap=cmap, norm=norm, extent=[xmin, xmax, ymin, ymax])
        main_heatmap_colorbar = self.figure.colorbar(
            cax, cax=data_colorbar_ax, orientation='vertical')

        main_heatmap_colorbar.set_label(
            f'{self.channel} [{self.dataMixin.units[self.channel]}]')

        # Plotting the residuals heatmap
        cax = ax4.imshow(residuals, aspect='auto', origin='lower', cmap=cmap, norm=colors.Normalize(
            vmin=residuals.min(), vmax=residuals.max()), extent=[xmin, xmax, ymin, ymax])
        residual_heatmap_colorbar = self.figure.colorbar(cax,
                                                         cax=residual_colorbar_ax, orientation='vertical')

        residual_heatmap_colorbar.set_label(f'Residual variation [{self.dataMixin.units[self.channel]}]')

        # Plotting the residual profile
        residual_profile_ax.plot(x_data, np.mean(residuals, axis=0))
        residual_profile_ax.margins(x=0)

        residual_profile_ax.set(xlabel="Distance [m]", ylabel=f"Residual variation[{self.dataMixin.units[self.channel]}]")
        residual_profile_ax.grid()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def calculate_residuals_and_variance(self, segments, md_variance, cd_variance):
        residuals = segments - np.mean(segments, axis=1, keepdims=True) - np.mean(segments, axis=0,
                                                                                  keepdims=True) + np.mean(segments)
        residual_variance = np.mean(residuals**2)
        return residuals, residual_variance

    def getStatsTableData(self):
        stats = []
        data = np.array(self.filtered_data)
        units = self.dataMixin.units[self.channel]
        total, md, cd, res = np.sqrt(self.calculate_variances(data))
        stats.append(["", f"{self.channel} [{units}]"])
        stats.append([
            "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
            f"{md:.2f}\n{cd:.2f}\n{total:.2f}\n{res:.2f}"
        ])

        mean = np.mean(data)
        stats.append(["", "% of mean"])
        stats.append([
            "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
            f"{(100 * md / mean):.2f}\n{(100 * cd / mean):.2f}\n{(100 * total / mean):.2f}\n{(100 * res / mean):.2f}"
        ])

        return stats

    def calculate_variances(self, segments):
        k, p = segments.shape  # Number of samples in MD and CD, respectively

        if k == 0 or p == 0:
            return 0, 0, 0, 0

        overall_mean = np.mean(segments)

        md_means = np.mean(segments, axis=1)
        cd_means = np.mean(segments, axis=0)

        Sa2 = np.sum((md_means - overall_mean)**2) / (k - 1)
        Sb2 = np.sum((cd_means - overall_mean)**2) / (p - 1)

        total_variance = np.sum((segments - overall_mean)**2) / (k * p - 1)

        residuals = segments - md_means[:, None] - cd_means + overall_mean
        residual_variance = np.sum(residuals**2) / ((k - 1) * (p - 1))

        md_variance = Sa2 - (1 / p) * residual_variance
        cd_variance = Sb2 - (1 / k) * residual_variance

        return total_variance, md_variance, cd_variance, residual_variance