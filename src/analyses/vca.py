from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox, QLabel
from PyQt6.QtGui import QAction
from utils.filters import bandpass_filter
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from matplotlib.ticker import MaxNLocator
from matplotlib import colors, cm
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    BandPassFilterMixin,
    SampleSelectMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    ControlsPanelWidget,
)
import settings
import numpy as np

analysis_name = "Variance Component Analysis"
analysis_types = ["CD"]

class AnalysisController(AnalysisControllerBase):
    band_pass_low: float
    band_pass_high: float
    analysis_range_low: float
    analysis_range_high: float
    remove_cd_variations: bool
    remove_md_variations: bool
    selected_samples: list[int]

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "CD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.set_default('band_pass_low', settings.VCA_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high', settings.VCA_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('analysis_range_low', settings.VCA_RANGE_LOW_DEFAULT * self.max_dist)
        self.set_default('analysis_range_high', settings.VCA_RANGE_HIGH_DEFAULT * self.max_dist)
        self.set_default('remove_cd_variations', settings.VCA_REMOVE_CD_VARIATIONS_DEFAULT)
        self.set_default('remove_md_variations', settings.VCA_REMOVE_MD_VARIATIONS_DEFAULT)
        self.set_default('selected_samples', self.measurement.selected_samples.copy())

    def plot(self):
        self.figure.clear()

        if len(self.selected_samples) == 0:
            self.canvas.draw()
            return

        # Calculate indices for slicing based on the analysis range
        low_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_high, side='right')

        # Preparation of data for plotting
        self.filtered_data = [bandpass_filter(
            self.measurement.segments[self.channel][sample_idx][low_index:high_index],
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

        x_data = self.measurement.cd_distances[low_index:high_index]

        # Plotting the MD mean profile
        md_mean = np.mean(self.filtered_data, axis=1)
        md_mean_ax.plot(md_mean, range(1, 1+len(md_mean)),
                        color='tab:blue', linewidth=2)

        md_mean_ax.set(
            xlabel=f"MD mean [{self.measurement.units[self.channel]}]", ylabel="Sample index")
        # TODO: Restrict the number of decimals here
        md_mean_ax.yaxis.set_major_locator(MaxNLocator(nbins=2, integer=True))
        md_mean_ax.xaxis.set_major_locator(MaxNLocator(nbins=2, integer=True))
        md_mean_ax.grid()

        md_mean_ax.margins(y=0)

        # Plotting the CD profile on top
        cd_profile_ax.plot(x_data, cd_mean_profile)
        cd_profile_ax.set(
            xlabel="Distance [m]", ylabel=f"CD mean [{self.measurement.units[self.channel]}]")
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
            f'{self.channel} [{self.measurement.units[self.channel]}]')

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def calculate_variances(self, segments):
        k, p = segments.shape  # Number of samples in MD and CD, respectively

        if k == 0 or p == 0:
            return 0, 0, 0, 0

        overall_mean = np.mean(segments)

        md_means = np.mean(segments, axis=1)
        cd_means = np.mean(segments, axis=0)

        # Sum of squares for MD (between samples)
        ss_md = p * np.sum((md_means - overall_mean)**2)
        # Sum of squares for CD (between positions within samples)
        ss_cd = k * np.sum((cd_means - overall_mean)**2)
        # Total sum of squares
        ss_total = np.sum((segments - overall_mean)**2)
        # Sum of squares for residuals (interaction)
        ss_residual = ss_total - ss_md - ss_cd

        # Degrees of freedom
        df_md = k - 1
        df_cd = p - 1
        df_residual = (k - 1) * (p - 1)
        df_total = k * p - 1

        # Mean squares (variances)
        ms_md = ss_md / df_md if df_md > 0 else 0
        ms_cd = ss_cd / df_cd if df_cd > 0 else 0
        ms_residual = ss_residual / df_residual if df_residual > 0 else 0

        # Variance components (as per ANSI/TAPPI T 545 om-08)
        # Note: These are estimates of variances, not mean squares directly.
        var_cd = (ms_cd - ms_residual) / k if k > 0 else 0
        var_md = (ms_md - ms_residual) / p if p > 0 else 0
        var_residual = ms_residual
        var_total = var_md + var_cd + var_residual

        # Ensure variances are not negative (can happen due to sampling variability)
        var_md = max(0, var_md)
        var_cd = max(0, var_cd)

        # Recalculate total based on potentially adjusted components
        var_total = var_md + var_cd + var_residual

        return var_total, var_md, var_cd, var_residual

    def calculate_residuals_and_variance(self, segments, md_variance, cd_variance):
        residuals = segments - np.mean(segments, axis=1, keepdims=True) - np.mean(segments, axis=0,
                                                                                  keepdims=True) + np.mean(segments)
        residual_variance = np.mean(residuals**2)
        return residuals, residual_variance

    def getStatsTableData(self):
        stats = []
        data = np.array(self.filtered_data)
        units = self.measurement.units[self.channel]

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


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "CD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self):
        viewMenu = self.menu_bar.addMenu('View')

        self.sampleSelectorWindow = None
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def update_remove_md_variations(self):
        state = self.removeMDVariationsCheckbox.isChecked()
        self.controller.remove_md_variations = state
        self.refresh()

    def update_remove_cd_variations(self):
        state = self.removeCDVariationsCheckbox.isChecked()
        self.controller.remove_cd_variations = state
        self.refresh()

    def initUI(self):
        self.setWindowTitle(f"{analysis_name} ({self.measurement.measurement_label})")
        # Geometry will be set by VCA_WINDOW_GEOMETRY from settings

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel, 0)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        self.controlsPanel.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)

        # VCA Specific Options Group
        vcaOptionsGroup = QGroupBox("VCA Options")
        vcaOptionsLayout = QVBoxLayout()
        vcaOptionsGroup.setLayout(vcaOptionsLayout)
        self.controlsPanel.addWidget(vcaOptionsGroup)

        self.removeMDVariationsCheckbox = QCheckBox("Remove MD variations")
        self.removeMDVariationsCheckbox.setChecked(self.controller.remove_md_variations)
        self.removeMDVariationsCheckbox.toggled.connect(self.update_remove_md_variations)
        vcaOptionsLayout.addWidget(self.removeMDVariationsCheckbox)

        self.removeCDVariationsCheckbox = QCheckBox("Remove CD variations")
        self.removeCDVariationsCheckbox.setChecked(self.controller.remove_cd_variations)
        self.removeCDVariationsCheckbox.toggled.connect(self.update_remove_cd_variations)
        vcaOptionsLayout.addWidget(self.removeCDVariationsCheckbox)


        # VCA Statistics Group
        vcaStatsGroup = QGroupBox("VCA Statistics")
        vcaStatsLayout = QVBoxLayout()
        vcaStatsGroup.setLayout(vcaStatsLayout)
        self.controlsPanel.addWidget(vcaStatsGroup)

        self.vcaChannelInfoLabel = QLabel("Channel: N/A") # Placeholder
        vcaStatsLayout.addWidget(self.vcaChannelInfoLabel)

        statsDisplayLayout = QHBoxLayout()
        self.vcaStatNamesLabel = QLabel("Names")
        self.vcaStatNamesLabel.setWordWrap(True)
        statsDisplayLayout.addWidget(self.vcaStatNamesLabel)

        self.vcaStatValuesLabel = QLabel("Values")
        self.vcaStatValuesLabel.setWordWrap(True)
        statsDisplayLayout.addWidget(self.vcaStatValuesLabel)

        self.vcaStatPercentagesLabel = QLabel("Percentages")
        self.vcaStatPercentagesLabel.setWordWrap(True)
        statsDisplayLayout.addWidget(self.vcaStatPercentagesLabel)

        vcaStatsLayout.addLayout(statsDisplayLayout)

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout() # This layout might now only contain the plot and toolbar
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Plotting area setup
        self.controller.addPlot(plotStatsLayout)

        self.setGeometry(*settings.VCA_WINDOW_GEOMETRY)
        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)

    def refresh(self):
        self.controller.updatePlot() # This will prepare self.controller.filtered_data
        self.refresh_widgets()
        self.updateVCAStatistics(self.controller.filtered_data) # Pass raw filtered_data

    def updateVCAStatistics(self, data): # 'data' here is filtered_data
        # This method should now prepare and display VCA stats using its own UI elements (e.g. QLabels)
        # For now, it will calculate vca_stats but not use StatsWidget
        vca_stats = self.controller.getStatsTableData() # This produces the list of lists for VCA's specific table

        if vca_stats:
            if len(vca_stats) > 0:
                # Assuming vca_stats[0] is like ["", "Channel [Unit]", "% of mean"]
                channel_info_text = "Statistics for: "
                if len(vca_stats[0]) > 1:
                    channel_info_text += vca_stats[0][1]
                self.vcaChannelInfoLabel.setText(channel_info_text)

            if len(vca_stats) > 1 and len(vca_stats[1]) == 3:
                # Assuming vca_stats[1] is [names_str, values_str, percents_str]
                self.vcaStatNamesLabel.setText(vca_stats[1][0])
                self.vcaStatValuesLabel.setText(vca_stats[1][1])
                self.vcaStatPercentagesLabel.setText(vca_stats[1][2])
            else:
                self.vcaStatNamesLabel.setText("N/A")
                self.vcaStatValuesLabel.setText("N/A")
                self.vcaStatPercentagesLabel.setText("N/A")
        else:
            self.vcaChannelInfoLabel.setText("Channel: N/A")
            self.vcaStatNamesLabel.setText("N/A")
            self.vcaStatValuesLabel.setText("N/A")
            self.vcaStatPercentagesLabel.setText("N/A")
