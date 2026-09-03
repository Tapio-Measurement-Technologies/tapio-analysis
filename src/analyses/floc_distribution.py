"""Floc distribution: how much of the sheet sits in flocs, and how long they are.

The formation index says how much small scale mass variation a sheet has. It
does not say what that variation looks like. The floc distribution answers the
second question: once the slow variation is filtered away, every contiguous
stretch that stays beyond a limit counts as one floc, and the result is how
much of the measured length those flocs take up, sorted by their length.

The analysed signal is the one the Formation window uses - basis weight
estimated from transmission by a least squares straight line fit - so a floc
here is a floc there. Any measured channel can be selected instead when the
question is about that channel's own structure (caliper bulges, for instance).

Reading the figure: with Limit+ = 1 g/m^2, a distribution value of 5 % at
2.4...3.2 mm means 5 % of the measured length consists of stretches between
2.4 and 3.2 mm long that run more than 1 g/m^2 above the local mean. The
cumulative curve at the same limit ends at the share of the length that is
beyond the limit at all.

Only the positive limit is entered. The other three follow it, as in the
legacy tool: Limit++ = 2 x Limit+, Limit- = -Limit+, Limit-- = -2 x Limit+.
"""

from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
                             QComboBox, QDoubleSpinBox, QMessageBox)
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.floc import (bin_centres_mm, floc_distribution, high_pass,
                        limit_set, usable_high_edge)
from utils.types import AnalysisType, PlotAnnotation
from analyses.formation import fit_linear
from gui.components import (
    AnalysisRangeMixin,
    SampleSelectMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    ControlsPanelWidget,
)
import settings
import numpy as np

analysis_name = "Floc Distribution"
analysis_types = ["MD", "CD"]


LIMIT_COLORS = {
    "Limit++": "#b2182b",
    "Limit+": "#ef8a62",
    "Limit-": "#67a9cf",
    "Limit--": "#2166ac",
}


class AnalysisController(AnalysisControllerBase):
    analysis_range_low: float
    analysis_range_high: float
    limit: float
    high_pass_1m: float
    selected_samples: list[int]

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)
        self.warning_message = None
        self.can_calculate = self.check_required_channels()
        self.sampleSelectorWindow = None
        self.floc_stats = []
        self.stats = np.array([])
        self.filtered_signal = np.array([])
        self.analysed_length_m = 0.0

        if self.window_type == "MD":
            self.set_default('analysis_range_low', settings.MD_FLOC_RANGE_LOW_DEFAULT * self.max_dist)
            self.set_default('analysis_range_high', settings.MD_FLOC_RANGE_HIGH_DEFAULT * self.max_dist)
        elif self.window_type == "CD":
            self.set_default('analysis_range_low', settings.CD_FLOC_RANGE_LOW_DEFAULT * self.max_dist)
            self.set_default('analysis_range_high', settings.CD_FLOC_RANGE_HIGH_DEFAULT * self.max_dist)

        self.set_default('selected_samples', self.measurement.selected_samples.copy())
        self.set_default('limit', settings.FLOC_LIMIT_DEFAULT)
        self.set_default('high_pass_1m', settings.FLOC_HIGH_PASS_DEFAULT_1M)

        # The base class has already put the first measured channel in
        # self.channel, so set_default would never fire. Open on the derived
        # basis weight instead, unless a saved analysis asked for a channel.
        if 'channel' not in attributes:
            self.channel = (self.available_channels[0]
                            if self.available_channels else None)

    def check_required_channels(self):
        """The derived basis weight needs the two channels the Formation window needs.

        Missing them is not fatal here: any measured channel can be analysed
        instead, so the derived channel is left out of the selector and the
        window opens on a measured one.
        """
        self.transmission_channel = settings.FORMATION_TRANSMISSION_CHANNEL
        try:
            self.bw_channel = settings.find_basis_weight_channel(
                self.measurement.channel_df)
        except ValueError:
            self.bw_channel = None

        if self.bw_channel is None or self.transmission_channel not in self.measurement.channels:
            self.bw_channel = None
            self.warning_message = (
                "Basis weight estimated from transmission is not available: "
                "the measurement needs both a basis weight and a transmission "
                "channel. Other channels can still be analysed.")

        return len(self.measurement.channels) > 0

    @property
    def available_channels(self):
        channels = list(self.measurement.channels)
        if self.bw_channel is not None:
            channels.insert(0, settings.FLOC_DERIVED_BW_LABEL)
        return channels

    @property
    def uses_derived_channel(self):
        return (self.channel == settings.FLOC_DERIVED_BW_LABEL
                and self.bw_channel is not None)

    @property
    def channel_unit(self):
        if self.uses_derived_channel:
            return self.measurement.units.get(self.bw_channel, "")
        return self.measurement.units.get(self.channel, "")

    def estimate_basis_weight(self, transmission, bw_reference):
        """Basis weight from transmission, by the Formation window's own fit.

        The fit is made against the measured basis weight of the same stretch,
        so the estimate carries the units and level of a basis weight
        measurement while keeping the resolution of transmission.
        """
        params = fit_linear(transmission, bw_reference)
        if params is None:
            return None
        return params[0] * np.asarray(transmission, dtype=float) + params[1]

    def analysis_profiles(self):
        """The profiles to analyse: one for MD, one per selected sample for CD.

        Returns an empty list when the selection yields no usable data, which
        the caller reports on the figure rather than raising.
        """
        if self.window_type == "MD":
            low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')

            def column(name):
                return np.asarray(
                    self.measurement.channel_df[name][low_index:high_index],
                    dtype=float)

            if self.uses_derived_channel:
                estimated = self.estimate_basis_weight(
                    column(self.transmission_channel), column(self.bw_channel))
                return [] if estimated is None else [estimated]

            if self.channel not in self.measurement.channels:
                return []
            return [column(self.channel)]

        low_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_low)
        high_index = np.searchsorted(
            self.measurement.cd_distances, self.analysis_range_high, side='right')

        def segments(name):
            available = self.measurement.segments.get(name)
            if available is None:
                return []
            return [np.asarray(available[index][low_index:high_index], dtype=float)
                    for index in self.selected_samples
                    if 0 <= index < len(available)]

        if self.uses_derived_channel:
            transmission = segments(self.transmission_channel)
            bw_profiles = segments(self.bw_channel)
            if not transmission or not bw_profiles:
                return []
            # One fit for the whole set, from the mean profiles, so that every
            # sample is converted on the same scale and their flocs stay
            # comparable. Fitting each sample separately would let the
            # conversion absorb the differences between samples.
            params = fit_linear(np.mean(transmission, axis=0),
                                np.mean(bw_profiles, axis=0))
            if params is None:
                return []
            return [params[0] * profile + params[1] for profile in transmission]

        if self.channel not in self.measurement.channels:
            return []
        return segments(self.channel)

    def calculate(self):
        """Filter, threshold and count. Returns (shares, cumulative, stats) per limit."""
        profiles = [profile for profile in self.analysis_profiles()
                    if len(profile) >= 2]
        if not profiles:
            return None

        # Filtered once here rather than once per limit: the four limits are
        # four thresholds on one signal. CD passes its profiles through
        # separately, so that no floc is counted across a sample boundary.
        filtered = [high_pass(profile, self.high_pass_1m, self.fs)
                    for profile in profiles]

        results = []
        for name, limit in limit_set(self.limit):
            shares, cumulative, statistics = floc_distribution(
                filtered, self.measurement.sample_step, limit,
                self.high_pass_1m, already_filtered=True)
            statistics["name"] = name
            results.append((shares, cumulative, statistics))

        self.filtered_signal = np.concatenate(filtered)
        self.analysed_length_m = (len(self.filtered_signal)
                                  * self.measurement.sample_step)
        return results

    def bin_centres_mm(self):
        return bin_centres_mm(self.measurement.sample_step)

    def plot(self):
        self.figure.clear()
        self.floc_stats = []
        self.stats = np.array([])

        channel_label = (settings.FLOC_DERIVED_BW_LABEL
                         if self.uses_derived_channel else self.channel)
        unit = self.channel_unit

        results = self.calculate() if self.can_calculate else None
        if not results:
            ax = self.figure.add_subplot(111)
            ax.axis('off')
            ax.text(0.5, 0.5,
                    "Floc distribution not available\n"
                    "(no usable data in the selected range or channel)",
                    ha='center', va='center', color='red')
            self.canvas.draw()
            self.updated.emit()
            return self.canvas

        # Three things on one figure: the distribution, the same numbers
        # accumulated, and the table the legacy tool put beside the plot.
        # Constrained layout, because the heading, the legend and the table are
        # all sized in points and would otherwise overrun the panels.
        self.figure.set_layout_engine("constrained")
        grid = self.figure.add_gridspec(3, 1, height_ratios=[2.0, 2.0, 1.0])
        distribution_ax = self.figure.add_subplot(grid[0])
        cumulative_ax = self.figure.add_subplot(grid[1], sharex=distribution_ax)
        table_ax = self.figure.add_subplot(grid[2])

        sizes = self.bin_centres_mm()
        for shares, cumulative, statistics in results:
            name = statistics["name"]
            color = LIMIT_COLORS.get(name)
            label = f"{name} = {statistics['limit']:.3g} {unit}".strip()
            # Steps, not a smooth line: each point is one sample count, and a
            # line between them would suggest floc sizes the sample step
            # cannot resolve.
            distribution_ax.plot(sizes, shares, drawstyle="steps-mid",
                                 color=color, lw=1.2, label=label)
            cumulative_ax.plot(sizes, cumulative, color=color, lw=1.2,
                               label=label)

        conditions = (f"{channel_label}, high pass {self.high_pass_1m:.3g} 1/m, "
                      f"{self.analysed_length_m:.1f} m analysed")
        self.figure.suptitle(
            f"{self.measurement.measurement_label} - Floc distribution\n"
            + conditions, fontsize=10)

        distribution_ax.set_ylabel("Share of length [%]")
        distribution_ax.grid(True, alpha=0.4)
        distribution_ax.legend(fontsize=8)
        distribution_ax.tick_params(labelbottom=False)

        cumulative_ax.set_xlabel(
            "Floc size [mm]   (the last bin holds every longer floc)")
        cumulative_ax.set_ylabel("Cumulative share [%]")
        cumulative_ax.grid(True, alpha=0.4)

        self.draw_statistics_table(table_ax, results, unit)

        # The high passed signal is what the limits are compared against, so
        # its spread is the number to choose a limit from.
        self.stats = self.filtered_signal
        self.floc_stats = [statistics for _shares, _cumulative, statistics in results]

        self.canvas.draw()
        self.updated.emit()
        return self.canvas

    def draw_statistics_table(self, ax, results, unit):
        ax.axis('off')
        columns = [f"Limit [{unit}]".strip(), "Exceeded [%]",
                   "Floc size [mm]", "Flocs / m", "Flocs"]
        rows = [statistics["name"] for _s, _c, statistics in results]
        cells = [[
            f"{statistics['limit']:.3g}",
            f"{statistics['exceeded_percent']:.1f}",
            f"{statistics['mean_size_mm']:.1f}" if np.isfinite(
                statistics['mean_size_mm']) else "-",
            f"{statistics['flocs_per_m']:.1f}" if np.isfinite(
                statistics['flocs_per_m']) else "-",
            f"{statistics['count']}",
        ] for _s, _c, statistics in results]

        table = ax.table(cellText=cells, rowLabels=rows, colLabels=columns,
                         cellLoc='center', rowLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.25)
        for index, (_s, _c, statistics) in enumerate(results):
            # Colour the row label to match the curve it belongs to.
            table[index + 1, -1].get_text().set_color(
                LIMIT_COLORS.get(statistics["name"], "black"))

    def getStatsTableData(self):
        """Rows for the report stats table: the numbers of the figure table."""
        if not self.floc_stats:
            return []

        def column(values):
            return "\n".join(values)

        unit = self.channel_unit
        names = [statistics["name"] for statistics in self.floc_stats]
        return [
            ["", f"Limit [{unit}]  Exceeded [%]  Floc size [mm]  Flocs/m".strip()],
            [
                column(names),
                column(
                    f"{statistics['limit']:.3g}      "
                    f"{statistics['exceeded_percent']:.1f}      "
                    f"{statistics['mean_size_mm']:.1f}      "
                    f"{statistics['flocs_per_m']:.1f}"
                    if np.isfinite(statistics['mean_size_mm'])
                    else f"{statistics['limit']:.3g}      0.0      -      -"
                    for statistics in self.floc_stats
                ),
            ],
        ]


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, SampleSelectMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        if not self.controller.can_calculate:
            QMessageBox.warning(
                self, "Floc distribution not available",
                self.controller.warning_message or "No channels to analyse")
            self.close()
            return
        self.initUI()

    def initMenuBar(self):
        viewMenu = self.menu_bar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        if settings.FLOC_TITLE_SHOW:
            self.setWindowTitle(
                f"Floc distribution ({self.measurement.measurement_label})")
        self.resize(*settings.FLOC_WINDOW_SIZE)

        if self.window_type == "CD":
            self.initMenuBar()

        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel, 0)

        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)

        analysisParamsLayout.addWidget(QLabel("Channel"))
        self.channelComboBox = QComboBox()
        self.channelComboBox.addItems(self.controller.available_channels)
        analysisParamsLayout.addWidget(self.channelComboBox)

        self.addAnalysisRangeSlider(analysisParamsLayout)

        self.limitLabel = QLabel("Limit+")
        analysisParamsLayout.addWidget(self.limitLabel)
        self.limitSpinBox = QDoubleSpinBox()
        self.limitSpinBox.setDecimals(settings.FLOC_LIMIT_DECIMALS)
        self.limitSpinBox.setRange(0.0, settings.FLOC_LIMIT_MAX)
        self.limitSpinBox.setSingleStep(settings.FLOC_LIMIT_STEP)
        analysisParamsLayout.addWidget(self.limitSpinBox)

        self.highPassLabel = QLabel("High pass [1/m]")
        analysisParamsLayout.addWidget(self.highPassLabel)
        self.highPassSpinBox = QDoubleSpinBox()
        self.highPassSpinBox.setDecimals(2)
        self.highPassSpinBox.setSingleStep(1.0)
        analysisParamsLayout.addWidget(self.highPassSpinBox)

        self.refresh_widgets()

        self.channelComboBox.currentIndexChanged.connect(self.channelChanged)
        self.limitSpinBox.valueChanged.connect(self.limitChanged)
        self.highPassSpinBox.valueChanged.connect(self.highPassChanged)

        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # The statistics are those of the high passed signal, which is what the
        # limits are compared against.
        self.stats_widget = StatsWidget()
        plotStatsLayout.addWidget(self.stats_widget)

        self.controller.addPlot(plotStatsLayout)

        self.refresh()

    def channelChanged(self):
        self.controller.channel = self.channelComboBox.currentText()
        self.refresh()

    def limitChanged(self):
        self.controller.limit = self.limitSpinBox.value()
        self.refresh()

    def highPassChanged(self):
        self.controller.high_pass_1m = self.highPassSpinBox.value()
        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)

        self.channelComboBox.blockSignals(True)
        index = self.channelComboBox.findText(self.controller.channel or "")
        if index >= 0:
            self.channelComboBox.setCurrentIndex(index)
        else:
            self.controller.channel = self.channelComboBox.currentText()
        self.channelComboBox.blockSignals(False)

        unit = self.controller.channel_unit
        self.limitLabel.setText(f"Limit+ [{unit}]" if unit else "Limit+")
        self.limitSpinBox.blockSignals(True)
        self.limitSpinBox.setValue(self.controller.limit)
        self.limitSpinBox.blockSignals(False)

        # The upper edge of the usable band, where the band pass controls
        # elsewhere also stop.
        highest = usable_high_edge(self.controller.fs)
        self.highPassSpinBox.blockSignals(True)
        self.highPassSpinBox.setRange(0.0, highest)
        self.highPassSpinBox.setValue(min(self.controller.high_pass_1m, highest))
        self.highPassSpinBox.blockSignals(False)
        self.controller.high_pass_1m = self.highPassSpinBox.value()

        cutoff = self.controller.high_pass_1m
        if cutoff > 0:
            self.highPassLabel.setText(
                f"High pass [1/m]\nkeeps λ ≤ {100.0 / cutoff:.1f} cm")
        else:
            self.highPassLabel.setText("High pass [1/m]\nno filtering")

    def refresh(self):
        self.controller.updatePlot()
        self.stats_widget.update_statistics(
            self.controller.stats, self.controller.channel_unit)
        self.refresh_widgets()
