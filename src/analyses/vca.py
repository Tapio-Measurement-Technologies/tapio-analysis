from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QGridLayout, QHBoxLayout, QCheckBox
from PyQt6.QtGui import QAction
from qtpy.QtCore import Qt
from utils.filters import bandpass_filter
from utils.data_loader import DataMixin
from matplotlib.ticker import MaxNLocator
from matplotlib import colors, cm
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    BandPassFilterMixin,
    SampleSelectMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    PlotMixin
)
import settings
import numpy as np

analysis_name = "Variance Component Analysis"
analysis_types = ["CD"]

class AnalysisController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, window_type="CD"):
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
        mean = np.mean(data)

        # Prevent division by zero
        md_percent = (100 * md / mean) if mean != 0 else 0
        cd_percent = (100 * cd / mean) if mean != 0 else 0
        total_percent = (100 * total / mean) if mean != 0 else 0
        res_percent = (100 * res / mean) if mean != 0 else 0

        # Define the statistics data structure for full data
        stat_data = [
            ("MD Stdev", f"{md:.2f}", f"{md_percent:.2f}"),
            ("CD Stdev", f"{cd:.2f}", f"{cd_percent:.2f}"),
            ("Total Stdev", f"{total:.2f}", f"{total_percent:.2f}"),
            ("Residual Stdev", f"{res:.2f}", f"{res_percent:.2f}")
        ]

        if settings.REPORT_FORMAT == "latex":
            stats.append(["", f"{self.channel} [{units}]", "% of mean"])
            for label, value, percent in stat_data:
                stats.append([f"{label}:", value, percent])

            # Add trimmed data section
            stats.append(["", "", ""])
            stats.append(["Edges removed", "", ""])

            # Remove 10% from start and end of each sample
            trimmed_data = [s[int(len(s) * 0.1): int(len(s) * 0.9)] for s in data]

            if trimmed_data:
                trimmed_data = np.array(trimmed_data)
                total_trimmed, md_trimmed, cd_trimmed, res_trimmed = np.sqrt(
                    self.calculate_variances(trimmed_data))
                mean_trimmed = np.mean(trimmed_data)

                # Prevent division by zero
                md_trimmed_percent = (100 * md_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                cd_trimmed_percent = (100 * cd_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                total_trimmed_percent = (100 * total_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                res_trimmed_percent = (100 * res_trimmed / mean_trimmed) if mean_trimmed != 0 else 0

                # Define the statistics data structure for trimmed data
                trimmed_stat_data = [
                    ("MD Stdev", f"{md_trimmed:.2f}", f"{md_trimmed_percent:.2f}"),
                    ("CD Stdev", f"{cd_trimmed:.2f}", f"{cd_trimmed_percent:.2f}"),
                    ("Total Stdev", f"{total_trimmed:.2f}", f"{total_trimmed_percent:.2f}"),
                    ("Residual Stdev", f"{res_trimmed:.2f}", f"{res_trimmed_percent:.2f}")
                ]

                stats.append(["", f"{self.channel} [{units}]", "% of mean"])
                for label, value, percent in trimmed_stat_data:
                    stats.append([f"{label}:", value, percent])
        else:
            stats.append(["", f"{self.channel} [{units}]", "% of mean"])
            labels = "\n".join(label + ":" for label, _, _ in stat_data)
            values = "\n".join(value for _, value, _ in stat_data)
            percents = "\n".join(percent + " %" for _, _, percent in stat_data)
            stats.append([labels, values, percents])

            stats.append(["", "", ""])
            stats.append(["Edges removed", "", ""])

            # Remove 10% from start and end of each sample
            trimmed_data = [s[int(len(s) * 0.1): int(len(s) * 0.9)] for s in data]

            if trimmed_data:
                trimmed_data = np.array(trimmed_data)
                total_trimmed, md_trimmed, cd_trimmed, res_trimmed = np.sqrt(
                    self.calculate_variances(trimmed_data))
                mean_trimmed = np.mean(trimmed_data)

                # Prevent division by zero
                md_trimmed_percent = (100 * md_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                cd_trimmed_percent = (100 * cd_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                total_trimmed_percent = (100 * total_trimmed / mean_trimmed) if mean_trimmed != 0 else 0
                res_trimmed_percent = (100 * res_trimmed / mean_trimmed) if mean_trimmed != 0 else 0

                # Define the statistics data structure for trimmed data
                trimmed_stat_data = [
                    ("MD Stdev", f"{md_trimmed:.2f}", f"{md_trimmed_percent:.2f}"),
                    ("CD Stdev", f"{cd_trimmed:.2f}", f"{cd_trimmed_percent:.2f}"),
                    ("Total Stdev", f"{total_trimmed:.2f}", f"{total_trimmed_percent:.2f}"),
                    ("Residual Stdev", f"{res_trimmed:.2f}", f"{res_trimmed_percent:.2f}")
                ]

                stats.append(["", f"{self.channel} [{units}]", "% of mean"])
                labels = "\n".join(label + ":" for label, _, _ in trimmed_stat_data)
                values = "\n".join(value for _, value, _ in trimmed_stat_data)
                percents = "\n".join(percent + " %" for _, _, percent in trimmed_stat_data)
                stats.append([labels, values, percents])

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


class AnalysisWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="CD", controller: AnalysisController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else AnalysisController()
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        fileMenu = menuBar.addMenu('File')
        viewMenu = menuBar.addMenu('View')

        self.sampleSelectorWindow = None
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def update_remove_md_variations(self):
        state = self.md_checkbox.isChecked()
        self.controller.remove_md_variations = state
        self.refresh()

    def update_remove_cd_variations(self):
        state = self.cd_checkbox.isChecked()
        self.controller.remove_cd_variations = state
        self.refresh()

    def initUI(self):
        self.setWindowTitle(
            f"Variance component analysis ({self.dataMixin.measurement_label})")
        self.setGeometry(*settings.VCA_WINDOW_GEOMETRY)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)
        # Add the channel selector
        self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)
        # Add statistics labels
        statsLayout = QGridLayout()
        self.total_std_dev_text = QLabel("Total standard deviation")
        self.md_std_dev_text = QLabel("MD standard deviation")
        self.cd_std_dev_text = QLabel("CD Standard deviation ")
        self.residual_std_dev_text = QLabel("Residual standard deviation")
        self.unit_label = QLabel("Unit")
        self.p_label = QLabel("% of mean")

        self.total_std_dev_label = QLabel("1")
        self.md_std_dev_label = QLabel("2")
        self.cd_std_dev_label = QLabel("3")
        self.residual_std_dev_label = QLabel("4")

        self.total_std_dev_p_label = QLabel("5")
        self.md_std_dev_p_label = QLabel("6")
        self.cd_std_dev_p_label = QLabel("7")
        self.residual_std_dev_p_label = QLabel("8")

        statsLayout.addWidget(self.unit_label, 0, 1)
        statsLayout.addWidget(self.p_label, 0, 2)

        statsLayout.addWidget(self.total_std_dev_text, 1, 0)
        statsLayout.addWidget(self.md_std_dev_text, 2, 0)
        statsLayout.addWidget(self.cd_std_dev_text, 3, 0)
        statsLayout.addWidget(self.residual_std_dev_text, 4, 0)

        statsLayout.addWidget(self.total_std_dev_label, 1, 1)
        statsLayout.addWidget(self.md_std_dev_label, 2, 1)
        statsLayout.addWidget(self.cd_std_dev_label, 3, 1)
        statsLayout.addWidget(self.residual_std_dev_label, 4, 1)

        statsLayout.addWidget(self.total_std_dev_p_label, 1, 2)
        statsLayout.addWidget(self.md_std_dev_p_label, 2, 2)
        statsLayout.addWidget(self.cd_std_dev_p_label, 3, 2)
        statsLayout.addWidget(self.residual_std_dev_p_label, 4, 2)

        mainLayout.addLayout(statsLayout)

        for label in [self.total_std_dev_label, self.md_std_dev_label, self.cd_std_dev_label, self.residual_std_dev_label]:
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)

        checkboxLayout = QHBoxLayout()
        self.md_checkbox = QCheckBox("Remove MD variations")
        self.md_checkbox.setChecked(False)
        self.md_checkbox.stateChanged.connect(self.update_remove_md_variations)
        checkboxLayout.addWidget(self.md_checkbox)
        self.cd_checkbox = QCheckBox("Remove CD variations")
        self.cd_checkbox.setChecked(False)
        self.cd_checkbox.stateChanged.connect(self.update_remove_cd_variations)
        checkboxLayout.addWidget(self.cd_checkbox)
        mainLayout.addLayout(checkboxLayout)

        self.plot = self.controller.getCanvas()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.updateVCAStatistics(self.controller.filtered_data)

    def updateVCAStatistics(self, data):

        vca_stats = {}
        data = np.array(data)
        total, md, cd, res = self.controller.calculate_variances(data)
        vca_stats["md_std_dev"] = np.sqrt(md)
        vca_stats["cd_std_dev"] = np.sqrt(cd)
        vca_stats["total_std_dev"] = np.sqrt(total)
        vca_stats["residual_std_dev"] = np.sqrt(res)

        mean = np.mean(data)

        vca_stats["md_std_dev_p"] = 100 * vca_stats["md_std_dev"] / mean
        vca_stats["cd_std_dev_p"] = 100 * vca_stats["cd_std_dev"] / mean
        vca_stats["total_std_dev_p"] = 100 * vca_stats["total_std_dev"] / mean
        vca_stats["residual_std_dev_p"] = 100 * \
            vca_stats["residual_std_dev"] / mean

        self.unit_label.setText(
            f"{self.dataMixin.units[self.controller.channel]}")
        self.total_std_dev_label.setText(f"{vca_stats['total_std_dev']:.2f}")
        self.md_std_dev_label.setText(f"{vca_stats['md_std_dev']:.2f}")
        self.cd_std_dev_label.setText(f"{vca_stats['cd_std_dev']:.2f}")
        self.residual_std_dev_label.setText(
            f"{vca_stats['residual_std_dev']:.2f}")

        self.total_std_dev_p_label.setText(
            f"{vca_stats['total_std_dev_p']:.2f}")
        self.md_std_dev_p_label.setText(f"{vca_stats['md_std_dev_p']:.2f}")
        self.cd_std_dev_p_label.setText(f"{vca_stats['cd_std_dev_p']:.2f}")
        self.residual_std_dev_p_label.setText(
            f"{vca_stats['residual_std_dev_p']:.2f}")
