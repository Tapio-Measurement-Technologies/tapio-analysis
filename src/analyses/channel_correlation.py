from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from scipy.stats import pearsonr
from utils.measurement import Measurement
from utils.filters import bandpass_filter
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from gui.components import (
    AnalysisRangeMixin,
    BandPassFilterMixin,
    SampleSelectMixin,
    ShowUnfilteredMixin,
    DoubleChannelMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
)
import settings
import numpy as np
import logging

analysis_name = "Channel Correlation"
analysis_types = ["MD", "CD"]

class AnalysisController(AnalysisControllerBase):
    selected_samples: list[int]
    channel1: str
    channel2: str
    show_unfiltered_data: bool
    band_pass_low: float
    band_pass_high: float
    analysis_range_low: float
    analysis_range_high: float

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        channel_correlation_config = {
            "MD": {
                "band_pass_low": settings.MD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.MD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT,
            },
            "CD": {
                "band_pass_low": settings.CD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M,
                "band_pass_high": settings.CD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M,
                "analysis_range_low": settings.CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT,
            }
        }

        self.channels = self.measurement.channels
        config = channel_correlation_config[self.window_type]

        self.set_default('selected_samples', self.measurement.selected_samples.copy())
        self.set_default('channel1', self.channels[0])
        self.set_default('channel2', self.channels[1])
        self.set_default('show_unfiltered_data', False)
        self.set_default('band_pass_low', config["band_pass_low"])
        self.set_default('band_pass_high', config["band_pass_high"])
        self.set_default('analysis_range_low', config["analysis_range_low"] * self.max_dist)
        self.set_default('analysis_range_high', config["analysis_range_high"] * self.max_dist)

    def calculate_max_cross_correlation_offset(self, data1, data2, sample_step):
        corr = np.correlate(data1 - np.mean(data1),
                            data2 - np.mean(data2), mode='full')
        max_corr_idx = np.argmax(corr) - (len(data1) - 1)
        offset_meters = max_corr_idx * sample_step * \
            settings.CORRELATION_ANALYSIS_DISPLAY_UNIT_MULTIPLIER
        return offset_meters

    def plot(self):
        self.figure.clear()
        ax_correlation = self.figure.add_subplot(211)

        ax1 = self.figure.add_subplot(212)

        # Plot for the first channel
        data1 = self.plotChannelData(ax1, self.channel1, 'tab:blue')

        # Adding a second Y axis for the second channel
        ax2 = ax1.twinx()
        data2 = self.plotChannelData(ax2, self.channel2, 'tab:green')

        corr_coeff, _ = pearsonr(data1, data2)
        ax_correlation.scatter(data1, data2, s=1)

        # Plot best-fit line
        if settings.CHANNEL_CORRELATION_SHOW_BEST_FIT:
            coeffs = np.polyfit(data1, data2, 1)
            fit_line = np.polyval(coeffs, data1)
            ax_correlation.plot(data1, fit_line, color='red', linestyle='--',
                                label=f"{self.channel2} = {coeffs[0]:.3f} * {self.channel1} + {coeffs[1]:.3f}")
            ax_correlation.legend()
            ax_correlation.set_title(f"Correlation coefficient: {corr_coeff:.2f}, {self.channel2} = {coeffs[0]:.3f} * {self.channel1} + {coeffs[1]:.3f}")


        else:
            ax_correlation.set_title(
                f"Correlation coefficient: {corr_coeff:.2f}")

        if settings.CHANNEL_CORRELATION_XCORR_OUTPUT:
            max_offset = self.calculate_max_cross_correlation_offset(
                data1, data2, self.measurement.sample_step)
            logging.info(f"Cross-correlation max at {max_offset:.2f} m ({1000*max_offset:.2f} mm)")


        ax_correlation.set_xlabel(
            f"{self.channel1} [{self.measurement.units[self.channel1]}]")
        ax_correlation.set_ylabel(
            f"{self.channel2} [{self.measurement.units[self.channel2]}]")
        ax_correlation.grid()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def plotChannelData(self, ax, channel, color):
        # This function needs to be adapted to how your data is structured and how you filter/prepare it
        if self.window_type == "MD":
            low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')

            x = self.measurement.distances[low_index:high_index]
            unfiltered_data = self.measurement.channel_df[channel][low_index:high_index]
            filtered_data = bandpass_filter(
                unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)
        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            x = self.measurement.cd_distances[low_index:high_index]

            unfiltered_data = np.mean([
                self.measurement.segments[channel][sample_idx][low_index:high_index]
                for sample_idx in self.selected_samples
            ],
                axis=0)

            filtered_data = bandpass_filter(
                unfiltered_data, self.band_pass_low, self.band_pass_high, self.fs)

        if self.show_unfiltered_data:
            ax.plot(x * settings.CORRELATION_ANALYSIS_DISPLAY_UNIT_MULTIPLIER,
                    unfiltered_data,
                    alpha=0.5,
                    color="gray")
        ax.plot(x * settings.CORRELATION_ANALYSIS_DISPLAY_UNIT_MULTIPLIER,
                filtered_data, color=color, alpha=0.9)
        ax.set_xlabel(
            f"Distance [{settings.CORRELATION_ANALYSIS_DISPLAY_UNIT}]")
        ax.set_ylabel(
            f"{channel} [{self.measurement.units[channel]}]", color=color)
        ax.tick_params(axis='y', labelcolor=color)
        # ax.grid()

        return filtered_data

    def getStatsTableData(self):
        stats = []
        return stats


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin, ShowUnfilteredMixin, DoubleChannelMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"{self.window_type.upper()} Channel correlation analysis ({
                            self.measurement.measurement_label})")
        self.setGeometry(*settings.CHANNEL_CORRELATION_WINDOW_GEOMETRY)

        if self.window_type == "CD":
            self.initMenuBar()

        # Main horizontal layout for controls and plot
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        controlsPanelLayout = QVBoxLayout()
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(settings.ANALYSIS_CONTROLS_PANEL_MIN_WIDTH)
        controlsWidget.setLayout(controlsPanelLayout)
        mainHorizontalLayout.addWidget(controlsWidget, 0)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        controlsPanelLayout.addWidget(dataSelectionGroup)
        self.addChannelSelectors(dataSelectionLayout)

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        controlsPanelLayout.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addBandPassRangeSlider(analysisParamsLayout)

        # Display Options Group
        displayOptionsGroup = QGroupBox("Display Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        controlsPanelLayout.addWidget(displayOptionsGroup)
        self.addShowUnfilteredCheckbox(displayOptionsLayout)

        controlsPanelLayout.addStretch()

        # Right panel for plot
        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotLayout)

        self.refresh()

    def initMenuBar(self):
        viewMenu = self.menu_bar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initShowUnfilteredCheckbox(block_signals=True)
        self.initChannelSelectors(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
