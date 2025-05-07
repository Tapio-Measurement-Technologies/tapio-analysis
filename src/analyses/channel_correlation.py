from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QMenuBar
from PyQt6.QtGui import QAction
from scipy.stats import pearsonr
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.measurement import Measurement
from utils.filters import bandpass_filter
from gui.components import (
    AnalysisRangeMixin,
    BandPassFilterMixin,
    SampleSelectMixin,
    ShowUnfilteredMixin,
    DoubleChannelMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    PlotMixin
)
import settings
import numpy as np
import logging

analysis_name = "Channel Correlation"
analysis_types = ["MD", "CD"]

class AnalysisController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, measurement: Measurement, window_type="MD"):
        super().__init__()
        self.measurement = measurement
        self.window_type = window_type

        if self.window_type == "MD":
            self.max_dist = np.max(self.measurement.distances)
            self.distances = self.measurement.distances
        elif self.window_type == "CD":
            self.max_dist = np.max(self.measurement.cd_distances)
            self.distances = self.measurement.cd_distances

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

        self.show_unfiltered_data = False
        self.selected_samples = self.measurement.selected_samples.copy()
        self.channels = self.measurement.channels
        self.channel1 = self.channels[0]
        self.channel2 = self.channels[0]
        config = channel_correlation_config[self.window_type]
        self.band_pass_low = config["band_pass_low"]
        self.band_pass_high = config["band_pass_high"]
        self.fs = 1 / self.measurement.sample_step
        self.analysis_range_low = config["analysis_range_low"] * self.max_dist
        self.analysis_range_high = config["analysis_range_high"] * \
            self.max_dist

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


class AnalysisWindow(QWidget, AnalysisRangeMixin, BandPassFilterMixin, SampleSelectMixin, ShowUnfilteredMixin, DoubleChannelMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="MD", controller: AnalysisController | None = None, measurement: Measurement | None = None):
        super().__init__()
        self.window_type = window_type
        self.controller = controller if controller else AnalysisController(
            measurement, window_type)
        self.measurement = self.controller.measurement
        self.sampleSelectorWindow = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f"{self.window_type.upper()} Channel correlation analysis ({
                            self.measurement.measurement_label})")

        self.setGeometry(100, 100, 700, 950)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Channel selectors
        self.addChannelSelectors(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)
        self.addBandPassRangeSlider(mainLayout)

        # Show unfiltered data checkbox
        self.addShowUnfilteredCheckbox(mainLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        viewMenu = menuBar.addMenu('View')
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
