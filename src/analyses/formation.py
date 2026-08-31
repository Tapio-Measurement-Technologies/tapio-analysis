from PyQt6.QtWidgets import QVBoxLayout, QMessageBox, QHBoxLayout, QGroupBox
from PyQt6.QtGui import QAction
from matplotlib import pyplot as plt
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from gui.components import (
    AnalysisRangeMixin,
    SampleSelectMixin,
    ShowProfilesMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    ControlsPanelWidget,
)
import settings
import numpy as np

analysis_name = "Formation"
analysis_types = ["MD", "CD"]


def fit_linear(x, y):
    """Ordinary least squares fit of y = a*x + b.

    Replaces scipy.optimize.curve_fit, which ran an iterative non-linear solver
    on what is a closed-form linear problem. Returns None if the fit is not
    defined (fewer than two finite points, or constant x).
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    common_length = min(len(x), len(y))
    x = x[:common_length]
    y = y[:common_length]

    finite_mask = np.isfinite(x) & np.isfinite(y)
    x = x[finite_mask]
    y = y[finite_mask]

    if len(x) < 2 or np.ptp(x) == 0:
        return None

    design = np.column_stack((x, np.ones_like(x)))
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return coefficients


def safe_correlation(x, y):
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    common_length = min(len(x), len(y))
    x = x[:common_length]
    y = y[:common_length]
    finite_mask = np.isfinite(x) & np.isfinite(y)
    x = x[finite_mask]
    y = y[finite_mask]
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


class AnalysisController(AnalysisControllerBase):
    analysis_range_low: float
    analysis_range_high: float
    show_profiles: bool
    selected_samples: list[int]

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)
        self.warning_message = None
        self.can_calculate = self.check_required_channels()
        self.sampleSelectorWindow = None

        if self.window_type == "MD":
            self.set_default('analysis_range_low', settings.MD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist)
            self.set_default('analysis_range_high', settings.MD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist)

        elif self.window_type == "CD":
            self.set_default('analysis_range_low', settings.CD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist)
            self.set_default('analysis_range_high', settings.CD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist)

        self.set_default('selected_samples', self.measurement.selected_samples.copy())
        self.set_default('show_profiles', False)

    def check_required_channels(self):
        """Check if all required channels exist and show alert if not."""
        missing_channels = []
        try:
            bw_channel = settings.find_basis_weight_channel(
                self.measurement.channel_df)
        except ValueError as error:
            missing_channels.append(str(error))
            bw_channel = None

        transmission_channel = settings.FORMATION_TRANSMISSION_CHANNEL
        if transmission_channel not in self.measurement.channels:
            missing_channels.append(f"Transmission ({transmission_channel})")

        if missing_channels:
            self.warning_message = f"Required channels not found: {', '.join(missing_channels)}"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("Formation Index Calculation Not Available")
            msg.setInformativeText(self.warning_message)
            msg.setWindowTitle("Missing Channels")
            msg.exec()
            return False

        self.channel = bw_channel
        self.transmission_channel = transmission_channel
        self.bw_channel = bw_channel
        return True

    def plot(self):
        self.figure.clear()
        self.stats = np.array([])
        self.correlation_coefficient = np.nan

        ax = self.figure.add_subplot(111)
        ax.set_title(
            f"{self.measurement.measurement_label} - Formation index ({self.channel})")
        params = {'mathtext.default': 'regular'}
        plt.rcParams.update(params)
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"$f_N$")
        ax.grid()

        if not self.can_calculate:
            self.figure.text(0.5, 0.5, "Formation Index calculation not available\nRequired channels missing",
                           ha='center', va='center', color='red')
            self.canvas.draw()
            self.stats = None  # Clear any previous stats
            return self.canvas

        # Todo: These are in meters, li
        # Todo: These are in meters, like distances array. Convert these to indices and have them have an effect on the displayed slice of the measurement
        if self.window_type == "MD":

            low_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.distances, self.analysis_range_high, side='right')

            x = self.measurement.distances[low_index:high_index]
            transmission_data = np.asarray(
                self.measurement.channel_df[self.transmission_channel][low_index:high_index],
                dtype=float,
            )
            bw_data = np.asarray(
                self.measurement.channel_df[self.bw_channel][low_index:high_index],
                dtype=float,
            )
            if min(len(transmission_data), len(bw_data)) < max(2, settings.FORMATION_WINDOW_LENGTH):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            params = fit_linear(transmission_data, bw_data)
            if params is None:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            estimated_bw = params[0] * transmission_data + params[1]

            self.correlation_coefficient = safe_correlation(bw_data, estimated_bw)

            y = self.calculate_formation_index(estimated_bw)

        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            x = self.measurement.cd_distances[low_index:high_index]

            transmission_data = [
                np.asarray(
                    self.measurement.segments[self.transmission_channel][sample_idx][low_index:high_index],
                    dtype=float,
                )
                for sample_idx in self.selected_samples
                if 0 <= sample_idx < len(self.measurement.segments[self.transmission_channel])
            ]
            bw_profiles = [
                np.asarray(
                    self.measurement.segments[self.bw_channel][sample_idx][low_index:high_index],
                    dtype=float,
                )
                for sample_idx in self.selected_samples
                if 0 <= sample_idx < len(self.measurement.segments[self.bw_channel])
            ]
            if (
                not transmission_data
                or not bw_profiles
                or min(len(transmission_data[0]), len(bw_profiles[0])) < max(2, settings.FORMATION_WINDOW_LENGTH)
            ):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            transmission_mean_profile = np.mean(transmission_data, axis=0)
            bw_mean_profile = np.mean(bw_profiles, axis=0)

            params = fit_linear(transmission_mean_profile, bw_mean_profile)
            if params is None:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            estimated_bw_profiles = [
                params[0] * profile + params[1] for profile in transmission_data]

            self.correlation_coefficient = safe_correlation(
                bw_mean_profile,
                np.mean(estimated_bw_profiles, axis=0),
            )
            formation_profiles = [self.calculate_formation_index(estimated_bw)
                                  for estimated_bw in estimated_bw_profiles]
            formation_profiles = [profile for profile in formation_profiles if len(profile) > 0]
            if not formation_profiles:
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            y = np.mean(formation_profiles, axis=0)

            if self.show_profiles:
                for i in formation_profiles:
                    ax.plot(x[settings.FORMATION_WINDOW_LENGTH-1:],
                            i, color="gray", alpha=0.5, lw=0.5)

        x = x[settings.FORMATION_WINDOW_LENGTH-1:]
        if len(x) == 0 or len(y) == 0:
            self.canvas.draw()
            self.updated.emit()
            return self.canvas

        show_unfiltered_data = True
        ax.plot(x, y)

        self.stats = y

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        if self.stats is None or len(self.stats) == 0:
            return stats

        mean = np.mean(self.stats)
        std = np.std(self.stats)
        min_val = np.min(self.stats)
        max_val = np.max(self.stats)
        # f_N = sigma_b / sqrt(b), so its unit is the square root of the basis
        # weight unit, not the basis weight unit itself.
        units = settings.FORMATION_INDEX_UNIT

        stats.append(["Correlation coefficient:",
                     f"{self.correlation_coefficient:.2f}"])
        stats.append(["", f"Formation index [{units}]"])
        stats.append([
            "Mean:\nStdev:\nMin:\nMax:",
            f"{mean:.2f}\n{std:.2f}\n{min_val:.2f}\n{max_val:.2f}"
        ])

        return stats

    def calculate_formation_index(self, arr, window_size=settings.FORMATION_WINDOW_LENGTH):
        """Sliding-window formation index f_N = sigma_b / sqrt(b), b = mean basis weight.

        Computed with running sums instead of a Python loop, which makes it O(N)
        rather than O(N * window_size). The data is centred on its own mean first
        so that the sum-of-squares term does not lose precision to cancellation
        when the mean is much larger than the standard deviation.

        Units: (g/m^2)^0.5.
        """
        values = np.asarray(arr, dtype=float).reshape(-1)
        window_size = int(window_size)
        num_values = len(values) - window_size + 1
        if window_size < 1 or num_values <= 0:
            return np.array([])

        offset = float(np.mean(values))
        centred = values - offset

        cumulative = np.concatenate(([0.0], np.cumsum(centred)))
        cumulative_squares = np.concatenate(([0.0], np.cumsum(centred ** 2)))

        window_sum = cumulative[window_size:] - cumulative[:-window_size]
        window_square_sum = (cumulative_squares[window_size:]
                             - cumulative_squares[:-window_size])

        centred_mean = window_sum / window_size
        # Clamp to zero: rounding can make an all-constant window slightly negative.
        variance = np.maximum(window_square_sum / window_size - centred_mean ** 2, 0.0)
        std = np.sqrt(variance)

        mean_value = centred_mean + offset
        sqrt_mean = np.sqrt(np.maximum(mean_value, 0.0))

        return np.divide(std, sqrt_mean, out=np.zeros_like(std), where=sqrt_mean > 0)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.sampleSelectorWindow = None
        if not self.controller.can_calculate:
            self.close()
            return
        self.initUI()

    def initMenuBar(self):
        viewMenu = self.menu_bar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def initUI(self):
        if settings.FORMATION_TITLE_SHOW:
            self.setWindowTitle(
                f"Formation analysis ({self.measurement.measurement_label})")
        self.resize(*settings.FORMATION_WINDOW_SIZE)

        if self.window_type == "CD":
            self.initMenuBar()

        # Main horizontal layout for controls and plot/stats
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel, 0)

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)

        if self.window_type == "CD":
            # Display Options Group (CD only)
            displayOptionsGroup = QGroupBox("Display Options")
            displayOptionsLayout = QVBoxLayout()
            displayOptionsGroup.setLayout(displayOptionsLayout)
            self.controlsPanel.addWidget(displayOptionsGroup)
            self.addShowProfilesCheckbox(displayOptionsLayout)


        # Right panel for plot and stats
        plotStatsLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotStatsLayout, 1)

        # Add statistics widget
        self.stats_widget = StatsWidget()
        plotStatsLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotStatsLayout)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        if self.window_type == "CD":
            self.initShowProfilesCheckbox(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.stats_widget.update_statistics(self.controller.stats, "")
        self.refresh_widgets()
