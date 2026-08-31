from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.plot_formatting import apply_compact_tick_formatting
from utils.types import AnalysisType, PlotAnnotation
from utils.filters import bandpass_filter_columns
import matplotlib.patheffects as path_effects
from matplotlib.ticker import MaxNLocator
from gui.components import (
    AnalysisRangeMixin,
    BandPassFilterMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    SampleSelectMixin,
    ControlsPanelWidget,
)
import settings
import logging
import numpy as np
import pandas as pd

analysis_name = "Correlation Matrix"
analysis_types = ["MD", "CD"]


def data_limits(values, padding=0.05):
    """Axis limits with a small margin, widened when the data is constant."""
    low = float(np.min(values))
    high = float(np.max(values))
    if not np.isfinite(low) or not np.isfinite(high):
        return -1.0, 1.0
    if low == high:
        return low - 0.5, high + 0.5
    margin = (high - low) * padding
    return low - margin, high + margin

class AnalysisController(AnalysisControllerBase):
    band_pass_low: float
    band_pass_high: float
    analysis_range_low: float
    analysis_range_high: float
    selected_samples: list[int]

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        setting_defaults = {
            "MD": {
                "band_pass_low": settings.MD_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.MD_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.MD_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist,
                "analysis_range_high": settings.MD_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist
            },
            "CD": {
                "band_pass_low": settings.CD_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.CD_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.CD_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist,
                "analysis_range_high": settings.CD_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist
            }
        }
        config = setting_defaults[self.window_type]

        self.set_default('band_pass_low', config["band_pass_low"])
        self.set_default('band_pass_high', config["band_pass_high"])
        self.set_default('analysis_range_low', config["analysis_range_low"])
        self.set_default('analysis_range_high', config["analysis_range_high"])
        self.set_default('selected_samples', self.measurement.selected_samples.copy())

    def plot(self):
        if self.measurement.channel_df.empty:
            logging.info("No data available for correlation matrix plot.")
            self.discard_panels()
            return

        def apply_bandpass_to_dataframe(df, lowcut, highcut, fs):
            # Every channel gets the same filter, so build the coefficients once
            # and convolve all channels in a single FFT pass instead of running
            # a separate transform per column.
            filtered = bandpass_filter_columns(
                df.to_numpy(dtype=float), lowcut, highcut, fs)
            return pd.DataFrame(filtered, columns=df.columns)

        if self.window_type == "MD":
            low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')
            data_slice = self.measurement.channel_df.iloc[low_index:high_index]

            data_slice = apply_bandpass_to_dataframe(
                data_slice, self.band_pass_low, self.band_pass_high, self.fs)

        elif self.window_type == "CD":
            if not self.selected_samples:
                logging.info("No samples selected for correlation matrix plot.")
                self.discard_panels()
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            cd_data_frame = pd.DataFrame(index=range(low_index, high_index))

            for channel in self.measurement.channels:
                segments = [
                    self.measurement.segments[channel][sample_idx][low_index:high_index]
                    for sample_idx in self.selected_samples
                ]
                channel_data = np.mean(segments, axis=0)
                cd_data_frame[channel] = channel_data

            data_slice = apply_bandpass_to_dataframe(
                cd_data_frame, self.band_pass_low, self.band_pass_high, self.fs)

        if len(data_slice) < 2:
            logging.info("Not enough data available for correlation matrix plot.")
            self.discard_panels()
            self.canvas.draw()
            self.updated.emit()
            return self.canvas

        self.data_slice = data_slice
        correlation_matrix = data_slice.corr()

        channels = list(data_slice.columns)
        for i in range(len(channels)):
            for j in range(i + 1, len(channels)):
                logging.info("%s to %s correlation: %.2f",
                             channels[i], channels[j], correlation_matrix.iloc[i, j])

        # Subsample only for the scatter panels; the correlations above use the
        # full slice. Sampling without replacement avoids drawing duplicated
        # points when the slice is shorter than the limit.
        sample_size = min(settings.CORRELATION_MATRIX_SAMPLE_LIMIT, len(data_slice))
        sampled_data_slice = data_slice.sample(n=sample_size, replace=False)
        sampled_columns = [
            sampled_data_slice[channel].to_numpy(dtype=float) for channel in channels]

        # Building a panel grid is by far the most expensive part of this plot,
        # so it is built once and afterwards only the data in it is replaced.
        # Moving a slider then costs a redraw instead of recreating every axes.
        if self.panels_reusable(channels):
            self.update_panels(sampled_columns, correlation_matrix)
        else:
            self.figure.clear()
            self.build_panels(channels, sampled_columns, correlation_matrix)

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def discard_panels(self):
        """Clear the figure and forget the cached grid."""
        self.figure.clear()
        self.axes = None
        self.panel_channels = None
        self.scatter_lines = {}
        self.histogram_patches = {}
        self.correlation_labels = {}
        self.column_anchors = {}
        self.row_anchors = {}

    def panels_reusable(self, channels):
        """True when the existing panel grid still matches the channels shown."""
        axes = getattr(self, "axes", None)
        if axes is None or getattr(self, "panel_channels", None) != channels:
            return False

        # A failed plot, or anything else that cleared the figure, invalidates
        # the cached axes even though they are still referenced here.
        expected = len(channels) * (len(channels) + 1) // 2
        return len(self.figure.axes) == expected

    def build_panels(self, channels, sampled_columns, correlation_matrix):
        """Create the lower-triangle panel grid and remember its artists."""
        channel_count = len(channels)

        # Only the lower triangle and the diagonal are drawn: the upper triangle
        # would show the same pairs with the axes swapped. Panels that are never
        # drawn are not created either, which is most of the cost of this plot.
        grid = self.figure.add_gridspec(channel_count, channel_count,
                                        hspace=0.06, wspace=0.06)
        axes = np.empty((channel_count, channel_count), dtype=object)
        self.scatter_lines = {}
        self.histogram_patches = {}
        self.correlation_labels = {}
        self.column_anchors = {}
        self.row_anchors = {}

        max_chars = settings.CORRELATION_MATRIX_TICK_LABEL_TARGET_CHARS
        label_font_size = settings.CORRELATION_MATRIX_LABEL_FONT_SIZE
        tick_formatters = []

        for row in range(channel_count):
            for column in range(row + 1):
                is_diagonal = row == column
                # Share the x range down each column and the y range across each
                # row, so tick locations are computed once per row and column.
                ax = self.figure.add_subplot(
                    grid[row, column],
                    sharex=self.column_anchors.get(column),
                    sharey=None if is_diagonal else self.row_anchors.get(row),
                )
                axes[row, column] = ax
                self.column_anchors.setdefault(column, ax)
                if not is_diagonal:
                    self.row_anchors.setdefault(row, ax)

                if is_diagonal:
                    _, _, patches = ax.hist(
                        sampled_columns[column],
                        bins=settings.CORRELATION_MATRIX_HISTOGRAM_BINS)
                    self.histogram_patches[column] = (ax, list(patches))
                    # The vertical axis here is a count, not a channel value.
                    ax.tick_params(axis='y', left=False, labelleft=False)
                else:
                    # A Line2D with markers draws far faster than a scatter's
                    # path collection, which dominated the render time.
                    line, = ax.plot(sampled_columns[column], sampled_columns[row],
                                    marker='.', linestyle='none', markersize=2,
                                    alpha=0.2)
                    self.scatter_lines[(row, column)] = line

                    annotation = ax.annotate(
                        f"{correlation_matrix.iloc[row, column]:.2f}", (0.5, 0.5),
                        xycoords='axes fraction', ha='center', va='center',
                        fontsize=10, weight='bold')
                    annotation.set_path_effects([
                        path_effects.Stroke(linewidth=2.5, foreground='white'),
                        path_effects.Normal()
                    ])
                    self.correlation_labels[(row, column)] = annotation

                ax.tick_params(axis='both', labelsize=6)
                # These panels are small; a few ticks is all that fits, and every
                # extra tick costs a Tick object on each of the panels.
                ax.xaxis.set_major_locator(MaxNLocator(nbins=3))
                ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
                ax.minorticks_off()

                shows_x_labels = row == channel_count - 1
                shows_y_labels = column == 0 and not is_diagonal

                if shows_x_labels:
                    ax.set_xlabel(channels[column], fontsize=label_font_size)
                else:
                    ax.tick_params(axis='x', labelbottom=False)

                if shows_y_labels:
                    ax.set_ylabel(channels[row], fontsize=label_font_size)
                elif not is_diagonal:
                    ax.tick_params(axis='y', labelleft=False)

                # Only format the labels that are actually shown; the formatter
                # searches over styles and precisions, so running it on hidden
                # axes is wasted work.
                if shows_x_labels or shows_y_labels:
                    tick_formatters.extend(apply_compact_tick_formatting(
                        ax, max_chars=max_chars,
                        x_axis=shows_x_labels, y_axis=shows_y_labels))

        if tick_formatters:
            label_width = max(formatter.label_width for formatter in tick_formatters)
            for formatter in tick_formatters:
                formatter.set_minimum_label_width(label_width)

        self.axes = axes
        self.panel_channels = list(channels)
        # Constrained layout re-solves the whole grid on every draw, which is
        # expensive for a panel grid this size and buys nothing here.
        self.figure.set_constrained_layout(False)
        self.figure.subplots_adjust(left=0.1, right=0.98, bottom=0.1, top=0.98)

    def update_panels(self, sampled_columns, correlation_matrix):
        """Replace the data in an existing panel grid, keeping the axes."""
        for (row, column), line in self.scatter_lines.items():
            line.set_data(sampled_columns[column], sampled_columns[row])

        for (row, column), annotation in self.correlation_labels.items():
            annotation.set_text(f"{correlation_matrix.iloc[row, column]:.2f}")

        for column, (ax, patches) in self.histogram_patches.items():
            counts, edges = np.histogram(sampled_columns[column], bins=len(patches))
            for index, patch in enumerate(patches):
                patch.set_bounds(edges[index], 0,
                                 edges[index + 1] - edges[index], counts[index])
            highest = counts.max()
            ax.set_ylim(0, highest * 1.05 if highest else 1)

        # The panels share limits by row and column, so setting the anchors is
        # enough to rescale the whole grid.
        for column, ax in self.column_anchors.items():
            ax.set_xlim(*data_limits(sampled_columns[column]))
        for row, ax in self.row_anchors.items():
            ax.set_ylim(*data_limits(sampled_columns[row]))

    def getStatsTableData(self):
        stats = []
        return stats

class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, BandPassFilterMixin, CopyPlotMixin, ChildWindowCloseMixin, SampleSelectMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initMenuBar(self):
        viewMenu = self.menu_bar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"Correlation matrix ({self.controller.measurement.measurement_label})")
        self.resize(*settings.CORRELATION_MATRIX_WINDOW_SIZE)

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
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)


        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        self.controller.addPlot(plotLayout)

        self.refresh()

    def refresh(self):
        self.controller.updatePlot()
