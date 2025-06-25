from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenuBar, QHBoxLayout, QGroupBox
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.filters import bandpass_filter
from utils.types import PlotAnnotation
from matplotlib.ticker import AutoMinorLocator
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    BandPassFilterMixin,
    ShowUnfilteredMixin,
    ShowTimeLabelsMixin,
    MachineSpeedMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    ExportMixin,
    ShowAnnotationsMixin
)
import settings
import numpy as np
import pandas as pd

analysis_name = "Time Domain"
analysis_types = ["MD"]

class AnalysisController(AnalysisControllerBase, ExportMixin):
    def __init__(self, measurement: Measurement, analysis_type="MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, analysis_type, annotations, attributes)

        self.max_dist = np.max(self.measurement.distances)
        self.fs = 1 / self.measurement.sample_step

        self.analysis_range_low = settings.TIME_DOMAIN_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist
        self.analysis_range_high = settings.TIME_DOMAIN_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist
        self.band_pass_low = settings.TIME_DOMAIN_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high = settings.TIME_DOMAIN_BAND_PASS_HIGH_DEFAULT_1M
        self.machine_speed = settings.PAPER_MACHINE_SPEED_DEFAULT
        self.show_unfiltered_data = settings.TIME_DOMAIN_SHOW_UNFILTERED_DATA_DEFAULT
        self.show_time_labels = settings.TIME_DOMAIN_SHOW_TIME_LABELS_DEFAULT

    def constrain_values(self):
        # This function constrains values in case they are set out of bounds by reporting
        if self.analysis_range_high > self.max_dist:
            self.analysis_range_high = self.max_dist

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the measurement

        low_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_high, side='right')

        self.distances = self.measurement.distances[low_index:high_index]
        if len(self.distances) <= 1:
            raise ValueError("Not enough data to plot")

        unfiltered_data = self.measurement.channel_df[self.channel][low_index:high_index]
        self.data = bandpass_filter(
            unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)
        self.constrain_values()

        if self.show_unfiltered_data:
            ax.plot(self.distances * settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER,
                    unfiltered_data,
                    alpha=0.5,
                    color="gray")
        ax.plot(self.distances *
                settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER, self.data)

        if settings.TIME_DOMAIN_FIXED_YLIM_ALL_DATA:
            # fixed y limits based on full unfiltered dataset
            full_data = self.measurement.channel_df[self.channel]
            y_min, y_max = full_data.min(), full_data.max()  # Get min and max values
            margin = 0.1 * (y_max - y_min)
            y_min -= margin
            y_max += margin
            ax.set_ylim(y_min, y_max)

        if settings.TIME_DOMAIN_TITLE_SHOW:
            ax.set_title(
                f"{self.measurement.measurement_label} ({self.channel})")
        if settings.TIME_DOMAIN_MINOR_GRID:
            ax.grid(True, which='both')
            ax.minorticks_on()
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(4))
            ax.grid(True, which='minor', linestyle=':', linewidth=0.5)
        else:
            ax.grid()

        ax.set_xlabel(
            f"Distance [{settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT}]")
        ax.set_ylabel(f"{self.channel} [{self.measurement.units[self.channel]}]")

        if settings.TIME_DOMAIN_FIXED_XTICKS:
            fixed_tick_positions = np.linspace(self.analysis_range_low, self.analysis_range_high,
                                               settings.TIME_DOMAIN_FIXED_XTICKS)
            ax.set_xticks(fixed_tick_positions)

        if self.show_time_labels:
            # Convert machine speed to meters per second
            machine_speed_m_per_s = self.machine_speed / 60.0
            # Calculate time in seconds from distances
            times = self.distances / machine_speed_m_per_s
            tick_positions = ax.get_xticks()
            tick_labels = np.interp(tick_positions / settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER,
                                    self.distances, times)
            ax2 = ax.secondary_xaxis('top')
            ax2.set_xlabel('Time [s]')
            ax2.set_xticks(tick_positions)
            ax2.set_xticklabels([f"{time:.2f}" for time in tick_labels])

        ax.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        if len(self.data) > 0:
            mean = np.mean(self.data)
            std = np.std(self.data)
            min_val = np.min(self.data)
            max_val = np.max(self.data)
            range_val = max_val - min_val
            std_percent = (std / mean) * 100 if mean != 0 else 0
            range_percent = (range_val / mean) * 100 if mean != 0 else 0
            units = self.measurement.units[self.channel]

            # Define the statistics data structure
            stat_data = [
                ("Mean", f"{mean:.2f}", units),
                ("Stdev", f"{std:.2f}", units),
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
                # stats.append(["", f"{self.channel} [{units}]"])
                stats.append(["", ""])
                labels = "\n".join(label + ":" for label, _, _ in stat_data)
                values = "\n".join(f"{value} {unit}" for _, value, unit in stat_data)
                stats.append([labels, values])

        return stats

    def getExportData(self):
        data = {"Distance [m]": self.distances, f"{
            self.channel} [{self.measurement.units[self.channel]}]": self.data}

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin,
                       ShowUnfilteredMixin, ShowTimeLabelsMixin, MachineSpeedMixin, CopyPlotMixin, ChildWindowCloseMixin, ShowAnnotationsMixin):

    def __init__(self, controller: AnalysisController, window_type="MD"):
        super().__init__(controller, window_type)
        self.measurement = self.controller.measurement
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)

        fileMenu = menuBar.addMenu('File')

        exportAction = self.controller.initExportAction(self, "Export current data")
        fileMenu.addAction(exportAction)

    def initUI(self):
        self.setWindowTitle(f"Time domain analysis ({self.measurement.measurement_label})")
        self.setGeometry(*settings.TIME_DOMAIN_WINDOW_GEOMETRY)

        # Main vertical layout for menu bar and the rest of the UI
        topLevelLayout = QVBoxLayout()
        self.setLayout(topLevelLayout)

        self.initMenuBar(topLevelLayout) # Menu bar at the top

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        topLevelLayout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        controlsPanelLayout = QVBoxLayout()
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(settings.ANALYSIS_CONTROLS_PANEL_MIN_WIDTH)
        controlsWidget.setLayout(controlsPanelLayout)
        mainHorizontalLayout.addWidget(controlsWidget)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Channel Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        controlsPanelLayout.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)
        self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display Options Group
        displayOptionsGroup = QGroupBox("Display Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        controlsPanelLayout.addWidget(displayOptionsGroup)
        self.addShowTimeLabelsCheckbox(displayOptionsLayout)
        self.addShowUnfilteredCheckbox(displayOptionsLayout)

        controlsPanelLayout.addStretch() # Add stretch to push control groups to the top

        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1) # Give more stretch to the plot/stats side

        # Add statistics widget
        self.stats_widget = StatsWidget()
        plotStatsLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        self.initShowUnfilteredCheckbox(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.updateStatistics(self.controller.data)

    def updateStatistics(self, profile_data):
        unit = self.measurement.units[self.controller.channel]
        self.stats_widget.update_statistics(profile_data, unit)




