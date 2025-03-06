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

        self.remove_cd_variations = False
        self.remove_md_variations = False

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
        cd_mean_profile = np.mean(self.filtered_data, axis=0)
        residuals, residual_variance = self.calculate_residuals_and_variance(
            np.array(self.filtered_data), 0, 0)

        # Setup the grid and axes
        gs = self.figure.add_gridspec(
            2, 3, width_ratios=[3, 16, 1], height_ratios=[3, 5], wspace=0.3, hspace=0.3)
        md_mean_ax = self.figure.add_subplot(gs[1, 0])
        cd_profile_ax = self.figure.add_subplot(gs[0, 1])
        cd_profile_ax.margins(x=0)
        ax2 = self.figure.add_subplot(gs[1, 1])
        ax2.yaxis.set_major_locator(MaxNLocator(integer=True))

        data_colorbar_ax = self.figure.add_subplot(gs[1, 2])

        x_data = self.dataMixin.cd_distances[low_index:high_index]

        # Plotting the MD mean profile
        md_mean = np.mean(self.filtered_data, axis=1)
        md_mean_ax.plot(md_mean, range(1, 1+len(md_mean)),
                        color='tab:blue', linewidth=2)

        md_mean_ax.set(
            xlabel=f"MD mean [{self.dataMixin.units[self.channel]}]", ylabel="Sample index")
        # TODO: Restrict the number of decimals here
        md_mean_ax.yaxis.set_major_locator(MaxNLocator(nbins=2, integer=True))
        md_mean_ax.xaxis.set_major_locator(MaxNLocator(nbins=2, integer=True))
        md_mean_ax.grid()

        md_mean_ax.margins(y=0)

        # Plotting the CD profile on top
        cd_profile_ax.plot(x_data, cd_mean_profile)
        cd_profile_ax.set(
            xlabel="Distance [m]", ylabel=f"CD mean [{self.dataMixin.units[self.channel]}]")
        cd_profile_ax.grid()

        self.plot_data = self.filtered_data

        md_mean = np.mean(self.filtered_data, axis=1, keepdims=True)
        md_mean -= np.mean(md_mean)
        cd_mean = np.mean(self.filtered_data, axis=0, keepdims=True)
        cd_mean -= np.mean(cd_mean)

        if self.remove_cd_variations:
            self.plot_data -= cd_mean

        if self.remove_md_variations:
            self.plot_data -= md_mean

        # Common settings for the colormap
        cmap = cm.get_cmap(settings.VCA_COLORMAP)
        norm = colors.Normalize(vmin=np.min(
            cd_mean_profile), vmax=(np.max(cd_mean_profile)))

        xmin, xmax = x_data[0], x_data[-1]
        ymin, ymax = 1, len(self.plot_data)

        # Plotting the main heatmap

        cax = ax2.imshow(self.plot_data, aspect='auto', origin='lower',
                         cmap=cmap, norm=norm, extent=[xmin, xmax, ymin, ymax])
        main_heatmap_colorbar = self.figure.colorbar(
            cax, cax=data_colorbar_ax, orientation='vertical')

        main_heatmap_colorbar.set_label(
            f'{self.channel} [{self.dataMixin.units[self.channel]}]')

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

        # Compute variances and take the square root to get standard deviations
        total, md, cd, res = np.sqrt(self.calculate_variances(data))

        # Compute mean
        mean = np.mean(data)

        # Prevent division by zero
        md_percent = (100 * md / mean) if mean != 0 else 0
        cd_percent = (100 * cd / mean) if mean != 0 else 0
        total_percent = (100 * total / mean) if mean != 0 else 0
        res_percent = (100 * res / mean) if mean != 0 else 0

        if settings.REPORT_FORMAT == "latex":
            stats.append(["", f"{self.channel} [{units}]", "% of mean"])
            stats.append(["MD Stdev:", f"{md:.2f}", f"{md_percent:.2f}"])
            stats.append(["CD Stdev:", f"{cd:.2f}", f"{cd_percent:.2f}"])
            stats.append(
                ["Total Stdev:", f"{total:.2f}", f"{total_percent:.2f}"])
            stats.append(
                ["Residual Stdev:", f"{res:.2f}", f"{res_percent:.2f}"])

        else:
            stats.append(["", f"{self.channel} [{units}]", "% of mean"])
            stats.append([
                "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
                f"{md:.2f}\n{cd:.2f}\n{total:.2f}\n{res:.2f}",
                f"{md_percent:.2f} %\n{cd_percent:.2f} %\n{
                    total_percent:.2f} %\n{res_percent:.2f} %"
            ])

            stats.append(["", "", ""])
            stats.append(["Edges removed", "", ""])

            # Remove 10% from start and end of each sample
            trimmed_data = [s[int(len(s) * 0.1): int(len(s) * 0.9)]
                            for s in data]

            if trimmed_data:
                trimmed_data = np.array(trimmed_data)

                # Compute trimmed statistics
                total_trimmed, md_trimmed, cd_trimmed, res_trimmed = np.sqrt(
                    self.calculate_variances(trimmed_data))
                mean_trimmed = np.mean(trimmed_data)

                # Prevent division by zero
                md_trimmed_percent = (
                    100 * md_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                cd_trimmed_percent = (
                    100 * cd_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                total_trimmed_percent = (
                    100 * total_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                res_trimmed_percent = (100 * res_trimmed /
                                       mean_trimmed) if mean_trimmed != 0 else 0

                stats.append(["", f"{self.channel} [{units}]", "% of mean"])
                stats.append([
                    "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
                    f"{md_trimmed:.2f}\n{cd_trimmed:.2f}\n{
                        total_trimmed:.2f}\n{res_trimmed:.2f}",
                    f"{md_trimmed_percent:.2f} %\n{cd_trimmed_percent:.2f} %\n{
                        total_trimmed_percent:.2f} %\n{res_trimmed_percent:.2f} %"
                ])

        return stats

    # def getStatsTableData(self):
    #     stats = []
    #     data = np.array(self.filtered_data)
    #     units = self.dataMixin.units[self.channel]
    #     total, md, cd, res = np.sqrt(self.calculate_variances(data))
    #     stats.append(["", f"{self.channel} [{units}]"])
    #     stats.append([
    #         "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
    #         f"{md:.2f}\n{cd:.2f}\n{total:.2f}\n{res:.2f}"
    #     ])

    #     mean = np.mean(data)
    #     stats.append(["", "% of mean"])
    #     stats.append([
    #         "MD Stdev:\nCD Stdev:\nTotal Stdev:\nResidual Stdev:",
    #         f"{(100 * md / mean):.2f}\n{(100 * cd / mean)
    #             :.2f}\n{(100 * total / mean):.2f}\n{(100 * res / mean):.2f}"
    #     ])

    #     return stats

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
