from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.filters import bandpass_filter
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.patheffects as path_effects
from gui.components import (
    AnalysisRangeMixin,
    BandPassFilterMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin
)
import settings
import logging
import numpy as np
import pandas as pd

analysis_name = "Correlation Matrix"
analysis_types = ["MD", "CD"]

class AnalysisController(AnalysisControllerBase):
    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        if window_type == "MD":
            self.max_dist = np.max(self.measurement.distances)
        elif window_type == "CD":
            self.max_dist = np.max(self.measurement.cd_distances)

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
        self.band_pass_low = config["band_pass_low"]
        self.band_pass_high = config["band_pass_high"]
        self.analysis_range_low = config["analysis_range_low"]
        self.analysis_range_high = config["analysis_range_high"]
        self.fs = 1 / self.measurement.sample_step

    def plot(self):
        if self.measurement.channel_df.empty:
            logging.info("No data available for correlation matrix plot.")
            return

        self.figure.clear()

        def apply_bandpass_to_dataframe(df, lowcut, highcut, fs):
            filtered_df = pd.DataFrame()
            for column in df.columns:
                filtered_df[column] = bandpass_filter(
                    df[column], lowcut, highcut, fs)
            return filtered_df

        if self.window_type == "MD":
            low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')
            data_slice = self.measurement.channel_df.iloc[low_index:high_index]

            data_slice = apply_bandpass_to_dataframe(
                data_slice, self.band_pass_low, self.band_pass_high, self.fs)

        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            cd_data_frame = pd.DataFrame(index=range(low_index, high_index))

            for channel, segments in self.measurement.segments.items():
                channel_data = np.mean(segments, axis=0)[low_index:high_index]
                print(channel)
                cd_data_frame[channel] = channel_data

            data_slice = apply_bandpass_to_dataframe(
                cd_data_frame, self.band_pass_low, self.band_pass_high, self.fs)

        correlation_matrix = data_slice.corr()

        channels = data_slice.columns
        for i in range(len(channels)):
            for j in range(i + 1, len(channels)):
                channel_x = channels[i]
                channel_y = channels[j]
                correlation_value = correlation_matrix.iloc[i, j]
                print(f"{channel_x} to {channel_y} correlation: {
                      correlation_value:.2f}")

        # or use .sample(n=500) for a fixed number of points
        sampled_data_slice = data_slice.sample(
            n=settings.CORRELATION_MATRIX_SAMPLE_LIMIT, replace=True)

        axes = pd.plotting.scatter_matrix(sampled_data_slice,
                                          alpha=0.2,
                                          figsize=(8, 8),
                                          ax=self.figure,
                                          diagonal="hist", hist_kwds={"bins": settings.CORRELATION_MATRIX_HISTOGRAM_BINS})

        # Adjust font size for axis labels
        for i in range(np.shape(axes)[0]):
            for j in range(np.shape(axes)[1]):
                axes[i, j].tick_params(axis='both', labelsize=6)  # Make tick labels smaller
                if i == len(axes)-1:  # Bottom row
                    axes[i, j].xaxis.label.set_fontsize(settings.CORRELATION_MATRIX_LABEL_FONT_SIZE)  # Make x-axis labels smaller
                if j == 0:  # Leftmost column
                    axes[i, j].yaxis.label.set_fontsize(settings.CORRELATION_MATRIX_LABEL_FONT_SIZE)  # Make y-axis labels smaller
                if i != j:
                    annotation = axes[i, j].annotate(f"{correlation_matrix.iloc[i, j]:.2f}", (0.5, 0.5),
                                        xycoords='axes fraction',
                                        ha='center',
                                        va='center',
                                        fontsize=10,
                                        weight='bold')
                    # Add white edge around text
                    annotation.set_path_effects([
                        path_effects.Stroke(linewidth=2.5, foreground='white'),
                        path_effects.Normal()
                    ])
                if i < j:
                    axes[i, j].set_visible(True)

        self.figure.set_constrained_layout(True)
        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        return stats

class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, BandPassFilterMixin, CopyPlotMixin, ChildWindowCloseMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.initUI()

    def initUI(self):
        self.setWindowTitle(
            f"Correlation matrix ({self.controller.measurement.measurement_label})")
        self.setGeometry(100, 100, 1000, 600)

        mainHorizontalLayout = QHBoxLayout()
        self.setLayout(mainHorizontalLayout)

        controlsPanelLayout = QVBoxLayout()
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(settings.ANALYSIS_CONTROLS_PANEL_MIN_WIDTH)
        controlsWidget.setLayout(controlsPanelLayout)
        mainHorizontalLayout.addWidget(controlsWidget, 0)

        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)

        controlsPanelLayout.addStretch()

        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        self.controller.addPlot(plotLayout)

        self.refresh()

    def refresh(self):
        self.controller.updatePlot()
