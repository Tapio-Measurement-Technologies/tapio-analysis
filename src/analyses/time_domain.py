from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QGroupBox
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.filters import bandpass_filter
from utils.statistics import normalized_least_squares_slope
from utils.types import PlotAnnotation
from matplotlib.ticker import AutoMinorLocator
from matplotlib.colors import to_rgb
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
    ShowAnnotationsMixin,
    ControlsPanelWidget,
)
import settings
from utils.plot_formatting import machine_speed_is_known
import numpy as np
import pandas as pd

analysis_name = "Time Domain"
analysis_types = ["MD"]

class AnalysisController(AnalysisControllerBase, ExportMixin):
    analysis_range_low: float
    analysis_range_high: float
    band_pass_low: float
    band_pass_high: float
    machine_speed: float
    show_unfiltered_data: bool
    show_time_labels: bool

    def __init__(self, measurement: Measurement, analysis_type="MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, analysis_type, annotations, attributes)

        self.set_default('analysis_range_low', settings.TIME_DOMAIN_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist)
        self.set_default('analysis_range_high', settings.TIME_DOMAIN_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist)
        self.set_default('band_pass_low', settings.TIME_DOMAIN_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high', settings.TIME_DOMAIN_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('machine_speed', settings.PAPER_MACHINE_SPEED_DEFAULT)
        self.set_default('show_unfiltered_data', settings.TIME_DOMAIN_SHOW_UNFILTERED_DATA_DEFAULT)
        self.set_default('fixed_ylim', settings.TIME_DOMAIN_FIXED_YLIM_ALL_DATA)
        self.set_default('show_time_labels', settings.TIME_DOMAIN_SHOW_TIME_LABELS_DEFAULT)

    def constrain_values(self):
        # This function constrains values in case they are set out of bounds by reporting
        if self.analysis_range_high > self.max_dist:
            self.analysis_range_high = self.max_dist

    def plot(self):
        # logging.info("Refresh")
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.figure.set_constrained_layout(True)
        ax.set_xlabel(
            f"Distance [{settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT}]")
        ax.set_ylabel(f"{self.channel} [{self.measurement.units[self.channel]}]")

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

        if settings.TIME_DOMAIN_FIXED_XTICKS:
            fixed_tick_positions = np.linspace(self.analysis_range_low, self.analysis_range_high,
                                               settings.TIME_DOMAIN_FIXED_XTICKS)
            ax.set_xticks(fixed_tick_positions)

        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the measurement

        low_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_high, side='right')

        self.distances = np.asarray(
            self.measurement.distances[low_index:high_index], dtype=float)
        unfiltered_data = np.asarray(
            self.measurement.channel_df[self.channel].iloc[low_index:high_index],
            dtype=float,
        ).reshape(-1)

        common_length = min(len(self.distances), len(unfiltered_data))
        self.distances = self.distances[:common_length]
        unfiltered_data = unfiltered_data[:common_length]

        if len(unfiltered_data) < 4:
            self.data = unfiltered_data
        else:
            self.data = np.asarray(
                bandpass_filter(
                    unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs),
                dtype=float,
            ).reshape(-1)
            common_length = min(len(self.distances), len(self.data))
            self.distances = self.distances[:common_length]
            self.data = self.data[:common_length]
            unfiltered_data = unfiltered_data[:common_length]
        self.constrain_values()

        color = settings.TIME_DOMAIN_COLOR
        shade = settings.TIME_DOMAIN_FILTERED_SHADE
        filtered_color = tuple(component * shade for component in to_rgb(color))
        unit = self.measurement.units[self.channel]
        x = self.distances * settings.TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER
        if self.show_unfiltered_data and len(self.distances):
            ax.plot(x, unfiltered_data,
                    color=color,
                    linewidth=settings.TIME_DOMAIN_UNFILTERED_LINEWIDTH,
                    alpha=settings.TIME_DOMAIN_UNFILTERED_ALPHA,
                    label=f"unfiltered, σ {np.std(unfiltered_data):.3g} {unit}")
        if len(self.distances):
            ax.plot(x, self.data,
                    color=filtered_color,
                    linewidth=settings.TIME_DOMAIN_FILTERED_LINEWIDTH,
                    label=(f"{self.filter_label()}, mean {np.mean(self.data):.4g} {unit}, "
                           f"σ {np.std(self.data):.3g} {unit}"))
        if settings.TIME_DOMAIN_SHOW_LEGEND and ax.get_legend_handles_labels()[0]:
            ax.legend(loc="upper right", fontsize=8, framealpha=0.85)

        if self.fixed_ylim:
            # The limits of the whole unfiltered record, so that every range
            # of this channel is drawn on the same scale. Percentiles rather
            # than the extremes, so one dropout does not flatten the trace.
            full_data = np.asarray(self.measurement.channel_df[self.channel], dtype=float)
            full_data = full_data[np.isfinite(full_data)]
            if len(full_data):
                y_min, y_max = np.percentile(full_data, [0.1, 99.9])
                margin = 0.1 * (y_max - y_min) or 1.0
                ax.set_ylim(y_min - margin, y_max + margin)

        # A machine speed of zero means the speed is not known, and distance
        # cannot be turned into time without it. The axis is left off rather
        # than divided by zero.
        if (self.show_time_labels and len(self.distances)
                and machine_speed_is_known(self.machine_speed)):
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

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def filter_label(self):
        """The band the filtered signal is, as the band pass controls write it."""
        low, high = float(self.band_pass_low), float(self.band_pass_high)
        if low > 0 and np.isfinite(high) and high > 0:
            return f"band-pass {low:g} - {high:g} 1/m"
        if np.isfinite(high) and high > 0:
            wavelength = 1.0 / high
            text = f"{wavelength:.3g} m" if wavelength >= 1.0 else f"{100 * wavelength:.3g} cm"
            return f"low-pass {high:g} 1/m (λ ≥ {text})"
        if low > 0:
            return f"high-pass {low:g} 1/m"
        return "unfiltered"

    def getStatsTableData(self):
        stats = []
        if len(self.data) > 0:
            mean = np.mean(self.data)
            std = np.std(self.data)
            min_val = np.min(self.data)
            max_val = np.max(self.data)
            range_val = max_val - min_val
            slope = normalized_least_squares_slope(self.data, self.distances)
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
                ("Range %", f"{range_percent:.2f}", "%"),
                ("Slope", f"{slope:.2f}", units)
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

    def initMenuBar(self):
        exportAction = self.controller.initExportAction(self, "Export current data")
        self.file_menu.addAction(exportAction)

    def initUI(self):
        self.setWindowTitle(f"Time domain analysis ({self.measurement.measurement_label})")
        self.resize(*settings.TIME_DOMAIN_WINDOW_SIZE)

        self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Channel Selection")
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
        self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display Options Group
        displayOptionsGroup = QGroupBox("Display Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        self.controlsPanel.addWidget(displayOptionsGroup)
        self.addShowTimeLabelsCheckbox(displayOptionsLayout)
        self.addShowUnfilteredCheckbox(displayOptionsLayout)


        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1) # Give more stretch to the plot/stats side

        # Add statistics widget
        self.stats_widget = StatsWidget(show_slope=True)
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
        self.stats_widget.update_statistics(
            profile_data, unit, self.controller.distances)




