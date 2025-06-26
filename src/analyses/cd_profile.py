from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.filters import bandpass_filter
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from scipy.stats import norm
from matplotlib.ticker import AutoMinorLocator
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    BandPassFilterMixin,
    SampleSelectMixin,
    StatsMixin,
    ShowProfilesMixin,
    ShowLegendMixin,
    ShowConfidenceIntervalMixin,
    ShowMinMaxMixin,
    WaterfallOffsetMixin,
    ExtraDataMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    ExportMixin
)
import settings
import numpy as np
import pandas as pd

analysis_name = "CD Profile"
analysis_types = ["CD"]

class AnalysisController(AnalysisControllerBase, ExportMixin):
    band_pass_low: float
    band_pass_high: float
    analysis_range_low: float
    analysis_range_high: float
    waterfall_offset: float
    confidence_interval: float | None
    show_profiles: bool
    show_min_max: bool
    show_legend: bool

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.mean_profile = None
        self.selected_samples = self.measurement.selected_samples.copy()
        self.max_dist = np.max(self.measurement.cd_distances)
        self.fs = 1 / self.measurement.sample_step
        self.set_default('band_pass_low', settings.CD_PROFILE_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high', settings.CD_PROFILE_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('analysis_range_low', settings.CD_PROFILE_RANGE_LOW_DEFAULT * self.max_dist)
        self.set_default('analysis_range_high', settings.CD_PROFILE_RANGE_HIGH_DEFAULT * self.max_dist)
        self.set_default('waterfall_offset', settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT)
        self.set_default('confidence_interval', None)
        self.set_default('show_profiles', False)
        self.set_default('show_min_max', False)
        self.set_default('show_legend', False)

        # Extra data
        self.extra_data = None
        self.extra_data_units = {}
        self.selected_sheet = None
        self.show_extra_data = False
        self.use_same_scale = False
        self.extra_data_adjust_start = 0
        self.extra_data_adjust_end = 0

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()

        if len(self.selected_samples) == 0:
            self.canvas.draw()
            return

        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the measurement

        low_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_high, side='right')

        x = self.measurement.cd_distances[low_index:high_index]

        unfiltered_data = [
            self.measurement.segments[self.channel][sample_idx][low_index:high_index]
            for sample_idx in self.selected_samples
        ]

        filtered_data = [bandpass_filter(
            i, self.band_pass_low, self.band_pass_high, self.fs) for i in unfiltered_data]

        self.mean_profile = np.mean(filtered_data, axis=0)
        std_error = np.std(filtered_data, axis=0) / np.sqrt(len(filtered_data))

        # Calculate the z-score for the given confidence level
        if self.confidence_interval is not None:
            z_score = norm.ppf(1 - (1 - self.confidence_interval) / 2)
            confidence_interval = z_score * std_error

        ax = self.figure.add_subplot(111)

        if self.show_profiles:
            for i in filtered_data:
                ax.plot(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                        i, alpha=0.2, color="gray")

        if self.show_min_max:
            ax.plot(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                    np.min(filtered_data, axis=0),
                    alpha=0.5,
                    color="red",
                    label="Minimum")
            ax.plot(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                    np.max(filtered_data, axis=0),
                    alpha=0.5,
                    color="green",
                    label="Maximum")

        ax.plot(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                self.mean_profile, label="Mean profile")
        if self.confidence_interval is not None:
            ax.fill_between(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                            self.mean_profile - confidence_interval,
                            self.mean_profile + confidence_interval,
                            color='tab:blue', alpha=0.3, label=f"{self.confidence_interval * 100}% CI")

        if settings.CD_PROFILE_TITLE_SHOW:
            ax.set_title(
                f"{self.measurement.measurement_label} ({self.channel})")

        if self.show_legend:

            handles, labels = ax.get_legend_handles_labels()
            if labels:  # This list will be non-empty if there are items to include in the legend
                ax.legend(handles, labels, loc="upper right")

        if settings.CD_PROFILE_MINOR_GRID:

            ax.grid(True, which='both')
            ax.minorticks_on()
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(4))
            ax.grid(True, which='minor', linestyle=':', linewidth=0.5)
        else:
            ax.grid()

        ax.set_xlabel(f"Distance [{settings.CD_PROFILE_DISPLAY_UNIT}]")
        ax.set_ylabel(
            f"{self.channel} [{self.measurement.units[self.channel]}]")

        # Add minimum range check
        if self.channel in settings.CD_PROFILE_MIN_RANGES:
            min_required = settings.CD_PROFILE_MIN_RANGES[self.channel]
            y_min, y_max = ax.get_ylim()
            current_range = y_max - y_min
            if current_range < min_required:
                mid = (y_max + y_min) / 2
                y_min_new = mid - min_required / 2
                y_max_new = mid + min_required / 2
                ax.set_ylim(y_min_new, y_max_new)

        if self.show_extra_data and self.selected_sheet and self.extra_data is not None:

            extra_data = self.extra_data[self.selected_sheet]
            unit = self.extra_data_units[self.selected_sheet]

            extra_x = extra_data.iloc[:, 0]
            extra_y = extra_data.iloc[:, 1]

            # Adjust the X values based on the sliders
            original_x = extra_x.values

            adjusted_first_x = original_x[0] + self.extra_data_adjust_start
            adjusted_last_x = original_x[-1] + self.extra_data_adjust_end

            original_range = original_x[-1] - original_x[0]
            adjusted_range = adjusted_last_x - adjusted_first_x

            extra_x = adjusted_first_x + \
                (original_x - original_x[0]) * \
                (adjusted_range / original_range)

            ax2 = ax.twinx()
            ax2.plot(extra_x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                        extra_y,
                        label=f"{self.selected_sheet} [{unit}]",
                        color="green")
            ax2.set_ylabel(f"{self.selected_sheet} [{
                            unit}]", color="tab:green")
            ax2.tick_params(axis='y', labelcolor='tab:green')

            # Also colour primary axis
            ax.set_ylabel(
                f"{self.channel} [{self.measurement.units[self.channel]}]", color="tab:blue")
            ax.tick_params(axis='y', labelcolor='tab:blue')

            if self.use_same_scale:
                if settings.FORCE_PRIMARY_SCALE_SUPPLEMENTARY:
                    ax2.set_ylim(ax.get_ylim())
                else:
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

    def getStatsTableData(self):
        stats = []
        if len(self.mean_profile) > 0:
            mean = np.mean(self.mean_profile)
            std = np.std(self.mean_profile)
            min_val = np.min(self.mean_profile)
            max_val = np.max(self.mean_profile)
            range_val = max_val - min_val
            std_percent = (std / mean) * 100 if mean != 0 else 0
            range_percent = (range_val / mean) * 100 if mean != 0 else 0
            units = self.measurement.units[self.channel]

            # Define the statistics data structure
            stat_data = [
                ("Mean", f"{mean:.2f}", units),
                ("Std", f"{std:.2f}", units),
                ("Std %", f"{std_percent:.2f}", "%"),
                ("Min", f"{min_val:.2f}", units),
                ("Max", f"{max_val:.2f}", units),
                ("Range", f"{range_val:.2f}", units),
                ("Range %", f"{range_percent:.2f}", "%")
            ]

            if settings.REPORT_FORMAT == "latex":
                stats.append(["", f"{self.channel}", ""])
                for label, value, unit in stat_data:
                    stats.append([f"{label}:", value, unit])
            else:
                stats.append(["", f"{self.channel} [{units}]"])
                labels = "\n".join(label + ":" for label, _, _ in stat_data)
                values = "\n".join(f"{value} {unit}" for _, value, unit in stat_data)
                stats.append([labels, values])

        return stats

    def getExportData(self):
        data = {
            "Distance [m]": self.measurement.cd_distances,
            f"{self.channel} [{self.measurement.units[self.channel]}]": self.mean_profile
        }

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin, ShowProfilesMixin, ShowLegendMixin, ShowConfidenceIntervalMixin, ShowMinMaxMixin, WaterfallOffsetMixin, ExtraDataMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type="CD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self):
        exportAction = self.controller.initExportAction(
            self, "Export mean profile")
        self.file_menu.addAction(exportAction)

        loadExtraDataAction = QAction('Load extra data', self)
        loadExtraDataAction.setShortcut("Ctrl+O")
        self.file_menu.addAction(loadExtraDataAction)
        loadExtraDataAction.triggered.connect(self.loadExtraData)

        viewMenu = self.menu_bar.addMenu('View')

        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"CD Profile ({self.measurement.measurement_label})")
        # Geometry will be set from settings CD_PROFILE_WINDOW_GEOMETRY

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        controlsPanelLayout = QVBoxLayout()
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(settings.ANALYSIS_CONTROLS_PANEL_MIN_WIDTH)
        controlsWidget.setLayout(controlsPanelLayout)
        mainHorizontalLayout.addWidget(controlsWidget, 0) # Controls take less space

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        controlsPanelLayout.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)
        # SampleSelector is handled by menu bar action

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)
        # No WaterfallOffsetSlider for the non-waterfall CD profile

        # Display Options Group
        displayOptionsGroup = QGroupBox("Display Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        controlsPanelLayout.addWidget(displayOptionsGroup)
        self.addShowProfilesCheckbox(displayOptionsLayout)
        self.addShowMinMaxCheckbox(displayOptionsLayout)
        self.addShowLegendCheckbox(displayOptionsLayout)
        self.addShowConfidenceIntervalCheckbox(displayOptionsLayout, settings.CD_PROFILE_CONFIDENCE_INTERVAL)

        # Extra Data Group
        extraDataGroup = QGroupBox("Overlay External Data")
        extraDataLayout = QVBoxLayout()
        extraDataGroup.setLayout(extraDataLayout)
        controlsPanelLayout.addWidget(extraDataGroup)
        self.addExtraDataWidget(extraDataLayout)

        controlsPanelLayout.addStretch()

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1) # Plot/stats take more space

        # Add statistics widget
        self.stats_widget = StatsWidget()
        plotStatsLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)

        self.setGeometry(*settings.CD_PROFILE_WINDOW_GEOMETRY)
        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        self.initShowLegendCheckbox(block_signals=True)
        self.initShowConfidenceIntervalCheckbox(block_signals=True)
        self.initShowMinMaxCheckbox(block_signals=True)
        self.initShowProfilesCheckbox(block_signals=True)

    def refresh(self):
        # logging.info("Refresh")
        self.controller.updatePlot()
        self.refresh_widgets()

        self.updateStatistics(self.controller.mean_profile)

    def updateStatistics(self, profile_data):
        unit = self.measurement.units[self.controller.channel]
        self.stats_widget.update_statistics(profile_data, unit)
