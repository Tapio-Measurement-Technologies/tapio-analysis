"""Floc distribution: how much of the sheet sits in flocs, and how long they are.

The formation index says how much small scale mass variation a sheet has. It
does not say what that variation looks like. The floc distribution answers the
second question: once the slow variation is filtered away, every contiguous
run of samples beyond a limit counts as one floc, and the result is how the
length those flocs cover divides between short flocs and long ones - with how
much of the sheet they cover at all reported beside it.

The analysed signal is the one the Formation window uses - basis weight
estimated from transmission by a least squares straight line fit - so a floc
here is a floc there. Any measured channel can be selected instead when the
question is about that channel's own structure (caliper bulges, for instance).

Reading the figure: the distribution is normalised within the flocs that were
found, so its bins add up to 100 % for every threshold that caught at least one
floc, and the cumulative curve ends at 100 %. A value of 20 % at 25.6 mm means
that a fifth of the length this threshold's flocs cover sits in flocs exactly
25.6 mm long. How much of the sheet those flocs cover in the first place is a
different number, and it is in the legend and in the table: the exceeded
percentage is still measured against the whole analysed length.

Only the positive limit is entered. The other three follow it, as in the legacy
tool: Limit++ = 2 x Limit+, Limit- = -Limit+, Limit-- = -2 x Limit+. Those names
are identifiers; the figure shows each limit as the condition it is, "> +2 g/m2"
and the like, in the unit of the analysed channel.
"""

from matplotlib.ticker import FuncFormatter, MultipleLocator
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
                             QComboBox, QDoubleSpinBox, QMessageBox)
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.floc import (bin_lengths_mm, floc_distribution, high_pass,
                        limit_set, threshold_label, usable_high_edge)
from utils.plot_formatting import compact_number_label, unit_label
from utils.types import AnalysisType, PlotAnnotation
from analyses.formation import fit_linear
from gui.components import (
    AnalysisRangeMixin,
    SampleSelectMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    ControlsPanelWidget,
)
import settings
import numpy as np

analysis_name = "Floc Distribution"
analysis_types = ["MD", "CD"]


# Warm for the excursions above the mean, cool for the ones below, and the
# stronger limit of each pair darker than the weaker one. The two signs are
# also drawn solid and dashed, because a sheet whose flocs are symmetric puts
# the two curves of a pair on top of each other and colour alone would then
# hide one of them completely.
LIMIT_STYLES = {
    "Limit++": {"color": "#b2182b", "dashes": ()},
    "Limit+": {"color": "#ef8a62", "dashes": ()},
    "Limit-": {"color": "#67a9cf", "dashes": (5, 2)},
    "Limit--": {"color": "#2166ac", "dashes": (5, 2)},
}
DEFAULT_STYLE = {"color": "black", "dashes": ()}


def number(value):
    """A statistic short enough for a legend or a table cell.

    One decimal, which is as far as any of these numbers is worth reading -
    except for a value too small for that, which would print as 0.0 and say
    the threshold caught nothing when it caught a thirtieth of a percent of
    the paper. Those get as many digits as they need to stay visible.
    """
    if not np.isfinite(value):
        return "-"
    if value != 0 and abs(value) < 0.05:
        return compact_number_label(value)
    return f"{value:.1f}"


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
        self.analysed_profile_count = 0

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
        # The main window passes None rather than an empty dict when there are
        # no saved attributes.
        if not attributes or 'channel' not in attributes:
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
        """Filter, threshold and count. Returns one FlocResult per limit."""
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
            result = floc_distribution(
                filtered, self.measurement.sample_step, limit,
                self.high_pass_1m, already_filtered=True)
            result.statistics["name"] = name
            results.append(result)

        self.filtered_signal = np.concatenate(filtered)
        self.analysed_length_m = (len(self.filtered_signal)
                                  * self.measurement.sample_step)
        self.analysed_profile_count = len(filtered)
        return results

    def bin_lengths_mm(self):
        return bin_lengths_mm(self.measurement.sample_step)

    def visible_bin_count(self, results):
        """How many bins are worth drawing: the occupied ones, plus one.

        A floc cannot be longer than about half the longest wavelength the high
        pass lets through, so on a coarse sample step most of the axis can
        never hold anything. Drawing all thirty bins then squeezes the whole
        distribution into the first centimetre of the panel and leaves the rest
        blank. The bins are all still calculated - only the view is cut, and
        only where every threshold is empty.
        """
        occupied = [int(np.max(np.nonzero(result.absolute_shares)[0]))
                    for result in results if np.any(result.absolute_shares)]
        if not occupied:
            return settings.FLOC_BIN_COUNT
        return min(settings.FLOC_BIN_COUNT, max(occupied) + 2)

    def configure_length_axis(self, ax, lengths, step_mm, visible):
        """Put the ticks on real floc lengths, and mark the last bin open ended.

        A locator rather than a fixed list of ticks, so that the axis still
        labels itself when the toolbar zooms in. Its step is a whole number of
        sample steps, because those are the only floc lengths the data can
        contain. The tick on the last bin is written with a ">=" when that bin
        is in view, because it is not one length but every floc at least that
        long; saying so on the tick is shorter than a sentence under the axis
        and cannot drift away from the bin it describes.
        """
        stride = max(1, int(round(visible / 6)))
        tick_step = stride * step_mm
        # Whole millimetres where the ticks fall on them, one decimal where a
        # sample step does not divide into them - 12.8 mm must not read as 13.
        decimals = 0 if abs(tick_step - round(tick_step)) < 0.05 else 1
        open_bin = float(lengths[-1]) if visible == len(lengths) else None

        def format_length(value, _position):
            text = f"{value:.{decimals}f}"
            if open_bin is not None and abs(value - open_bin) < 0.25 * step_mm:
                return f"\u2265{text}"
            return text

        ax.xaxis.set_major_locator(MultipleLocator(tick_step))
        ax.xaxis.set_major_formatter(FuncFormatter(format_length))

    def analysed_length_label(self):
        """How much paper the percentages are measured against.

        A CD analysis pools several sample profiles, and it is their total
        length that the exceeded percentage is a share of, so the number of
        samples is said as well rather than leaving the length looking like one
        profile's.
        """
        if self.analysed_length_m >= 1.0:
            length = f"{self.analysed_length_m:.0f} m analysed"
        else:
            length = f"{1000.0 * self.analysed_length_m:.0f} mm analysed"
        if self.analysed_profile_count > 1:
            return f"{self.analysed_profile_count} samples, {length}"
        return length

    def metadata_line(self, channel_label):
        """The one line under the heading: what was measured, how, and how much.

        It ends with the definition of a floc because that is the one thing the
        figure cannot show and a reader cannot guess, and it is short enough to
        share the line rather than becoming a paragraph on the plot.
        """
        filtering = (f"high-pass {self.high_pass_1m:g} m\u207b\u00b9"
                     if self.high_pass_1m > 0 else "no high-pass filter")
        return (f"{channel_label} \u2022 {filtering} \u2022 "
                f"{self.analysed_length_label()} \u2022 "
                "floc = one continuous run beyond the threshold")

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
                    "Floc length distribution not available\n"
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

        lengths = self.bin_lengths_mm()
        for result in results:
            statistics = result.statistics
            style = LIMIT_STYLES.get(statistics["name"], DEFAULT_STYLE)
            # The legend carries what the normalised curves cannot: how much of
            # the sheet is beyond this threshold at all. Without it every curve
            # would end at 100 % and a threshold that caught a twentieth of the
            # paper would look like one that caught a quarter of it.
            label = (f"{threshold_label(statistics['limit'], unit)}   "
                     f"({number(statistics['exceeded_percent'])} % of length)")
            # Steps, not a smooth line: each point is one sample count, and a
            # line between them would suggest floc lengths the sample step
            # cannot resolve.
            distribution_ax.plot(lengths, result.shares, drawstyle="steps-mid",
                                 color=style["color"], lw=1.2,
                                 dashes=style["dashes"], label=label)
            cumulative_ax.plot(lengths, result.cumulative, color=style["color"],
                               lw=1.2, dashes=style["dashes"], label=label)

        # MD or CD in front of the name, unless the name already says it.
        name = self.measurement.measurement_label or ""
        direction = ("" if name.upper().startswith(self.window_type)
                     else self.window_type)
        heading = " ".join(part for part in (direction, name) if part)
        self.figure.suptitle(
            f"{heading} \u2014 Floc length distribution".strip(" \u2014"),
            fontsize=10)
        distribution_ax.set_title(self.metadata_line(channel_label), fontsize=8)

        step_mm = 1000.0 * self.measurement.sample_step
        visible = self.visible_bin_count(results)

        for ax in (distribution_ax, cumulative_ax):
            ax.grid(True, alpha=0.4)
        distribution_ax.set_xlim(lengths[0] - 0.5 * step_mm,
                                 lengths[visible - 1] + 0.5 * step_mm)
        # A shared x axis, so this reaches the distribution panel as well.
        self.configure_length_axis(cumulative_ax, lengths, step_mm, visible)

        distribution_ax.set_ylabel("Share of floc-\ncovered length [%]")
        distribution_ax.set_ylim(bottom=0)
        distribution_ax.legend(fontsize=8)
        distribution_ax.tick_params(labelbottom=False)

        cumulative_ax.set_xlabel("Floc length [mm]")
        cumulative_ax.set_ylabel("Cumulative floc-\ncovered length [%]")
        # Normalised curves, so every threshold that found a floc ends at 100.
        # A tick there is enough to show it; a line across the panel is not.
        cumulative_ax.set_ylim(0, 105)
        cumulative_ax.set_yticks([0, 20, 40, 60, 80, 100])

        self.draw_statistics_table(table_ax, results, unit)

        # The high passed signal is what the limits are compared against, so
        # its spread is the number to choose a limit from.
        self.stats = self.filtered_signal
        self.floc_stats = [result.statistics for result in results]

        self.canvas.draw()
        self.updated.emit()
        return self.canvas

    def draw_statistics_table(self, ax, results, unit):
        """The absolute numbers, which the normalised curves deliberately drop.

        Nothing here is normalised: the exceeded percentage is of the whole
        analysed length, and the mean length and the count are of the flocs as
        they were detected.
        """
        ax.axis('off')
        columns = ["Threshold", "Length beyond [%]", "Mean length [mm]",
                   "Flocs / m", "Count"]
        cells = [[
            threshold_label(statistics['limit'], unit),
            number(statistics['exceeded_percent']),
            number(statistics['mean_size_mm']),
            number(statistics['flocs_per_m']),
            f"{statistics['count']}",
        ] for _shares, _cumulative, statistics, _absolute in results]

        table = ax.table(cellText=cells, colLabels=columns,
                         cellLoc='center', loc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.0, 1.25)
        for index, result in enumerate(results):
            # The threshold reads in the colour of the curve it belongs to.
            table[index + 1, 0].get_text().set_color(
                LIMIT_STYLES.get(result.statistics["name"],
                                 DEFAULT_STYLE)["color"])

    def getStatsTableData(self):
        """Rows for the report stats table: the numbers of the figure table."""
        if not self.floc_stats:
            return []

        def column(values):
            return "\n".join(values)

        unit = self.channel_unit
        thresholds = [threshold_label(statistics["limit"], unit)
                      for statistics in self.floc_stats]
        return [
            ["Threshold", "Length beyond [%]  Mean length [mm]  Flocs/m"],
            [
                column(thresholds),
                column(
                    f"{number(statistics['exceeded_percent'])}      "
                    f"{number(statistics['mean_size_mm'])}      "
                    f"{number(statistics['flocs_per_m'])}"
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
                self, "Floc length distribution not available",
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
                f"Floc length distribution "
                f"({self.measurement.measurement_label})")
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

        self.limitLabel = QLabel("Threshold")
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

        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        self.controller.addPlot(plotLayout)

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

        # The control sets one number and the figure applies four thresholds
        # to it, so the label says so rather than leaving the other three to be
        # discovered from the legend.
        unit = unit_label(self.controller.channel_unit)
        self.limitLabel.setText(
            f"Threshold [{unit}]\n\u00b1 this and \u00b12 \u00d7 this" if unit
            else "Threshold\n\u00b1 this and \u00b12 \u00d7 this")
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
        self.refresh_widgets()
