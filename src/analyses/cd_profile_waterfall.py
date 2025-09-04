from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.filters import bandpass_filter
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
import matplotlib.pyplot as plt
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
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    ExportMixin,
    ControlsPanelWidget
)
import settings
import numpy as np
import pandas as pd

analysis_name = "CD Profile (Waterfall)"
analysis_types = ["CD"]


class AnalysisController(AnalysisControllerBase, ExportMixin):
    band_pass_low: float
    band_pass_high: float
    analysis_range_low: float
    analysis_range_high: float
    waterfall_offset: float
    selected_samples: list[int]

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.mean_profile = None

        initial_waterfall_offset = settings.CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS.get(
            self.channel,
            settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT
        ) if settings.CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS is not None else settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT

        self.set_default(
            'band_pass_low', settings.CD_PROFILE_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high',
                         settings.CD_PROFILE_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('analysis_range_low',
                         settings.CD_PROFILE_RANGE_LOW_DEFAULT * self.max_dist)
        self.set_default('analysis_range_high',
                         settings.CD_PROFILE_RANGE_HIGH_DEFAULT * self.max_dist)
        self.set_default('waterfall_offset',
                         initial_waterfall_offset)
        self.set_default('selected_samples',
                         self.measurement.selected_samples.copy())

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

        tableau_color_cycle = plt.get_cmap('tab10')

        y_offset = self.waterfall_offset
        ax = self.figure.add_subplot(111)

        y_ticks = []
        y_tick_labels = []

        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_tick_labels)

        ax.set_ylim(1*self.waterfall_offset, -1 *
                    self.waterfall_offset * (len(self.selected_samples)))

        for offset_index, sample_idx in enumerate(self.selected_samples):
            unfiltered_data = self.measurement.segments[self.channel][sample_idx][low_index:high_index]
            filtered_data = bandpass_filter(
                unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)

            # Remove mean

            filtered_data -= np.mean(filtered_data)
            filtered_data *= -1

            color = tableau_color_cycle(sample_idx % 10)
            ax.plot(x * settings.CD_PROFILE_DISPLAY_UNIT_MULTIPLIER,
                    filtered_data - offset_index * y_offset,
                    lw=1,
                    alpha=0.9,
                    color=settings.CD_PROFILE_WATERFALL_COLOR if settings.CD_PROFILE_WATERFALL_COLOR else color)

            # Calculate mean and add horizontal line
            mean_value = -1 * offset_index * y_offset
            ax.axhline(mean_value, color='gray',
                       linestyle='-', linewidth=1)

            if offset_index == 0:
                ax.text(
                    0.10, 1.05,
                    f"Sample spacing\n{y_offset:.2f} {
                        self.measurement.units[self.channel]}",
                    ha='center',
                    va='center',
                    fontsize=8,
                    color="tab:gray",
                    transform=ax.transAxes
                )

            ax.text(
                x[0] - 0.07 * (x[-1] - x[0]),
                mean_value,
                f"{offset_index + 1}",
                ha='center',
                va='center',
                fontsize=10,
                color="black"
            )

        if settings.CD_PROFILE_TITLE_SHOW:
            ax.set_title(
                f"{self.measurement.measurement_label} ({self.channel})")
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
        ax.set_xlabel("Distance [m]")
        # ax.set_ylabel("Sample Index")
        # ax.set_zlabel(
        #     f"{self.channel} [{self.measurement.units[self.channel]}]")

        # ax.view_init(25, -130)

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
                values = "\n".join(f"{value} {unit}" for _,
                                   value, unit in stat_data)
                stats.append([labels, values])

        return stats

    def getExportData(self):
        data = {
            "Distance [m]": self.measurement.cd_distances,
            f"{self.channel} [{self.measurement.units[self.channel]}]": self.mean_profile
        }

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin, StatsMixin, ShowProfilesMixin, ShowLegendMixin, ShowConfidenceIntervalMixin, ShowMinMaxMixin, WaterfallOffsetMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type="CD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self):
        fileMenu = self.file_menu
        exportAction = self.controller.initExportAction(
            self, "Export mean profile")
        fileMenu.addAction(exportAction)

        viewMenu = self.menu_bar.addMenu('View')

        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"CD Profile (Waterfall) ({self.measurement.measurement_label})")
        # Geometry will be set from settings

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(
            self.controlsPanel, 0)  # Controls take less space

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        self.controlsPanel.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)
        # SampleSelector is handled by menu bar action

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)
        self.addWaterfallOffsetSlider(analysisParamsLayout)

        # Disable the offset slider if default offsets for channels are configured
        if settings.CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS is not None:
            self.waterfallOffsetSlider.setEnabled(False)
            self.waterfallOffsetSlider.setToolTip(
                "Adjustment disabled due to channel-specific default offsets configured in settings.")

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        # Plot/stats take more space
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Add statistics widget
        self.stats_widget = StatsWidget()
        plotStatsLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)

        # Uses same as cd_profile
        self.setGeometry(*settings.CD_PROFILE_WINDOW_GEOMETRY)
        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)

    def refresh(self):
        # logging.info("Refresh")
        self.controller.updatePlot()
        self.refresh_widgets()

        self.updateStatistics(self.controller.mean_profile)

    def updateStatistics(self, profile_data):
        unit = self.measurement.units[self.controller.channel]
        self.stats_widget.update_statistics(profile_data, unit)

    def on_channel_changed(self, channel):
        if settings.CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS is None:
            # Do not change offsets if not explicitly configured in settings.py
            return

        waterfall_offset = settings.CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS.get(
            channel,
            settings.CD_PROFILE_WATERFALL_OFFSET_DEFAULT
        )
        self.controller.waterfall_offset = waterfall_offset
        self.waterfallOffsetSlider.setValue(waterfall_offset)
