from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QMessageBox
from PyQt6.QtGui import QAction
from qtpy.QtCore import Qt
from matplotlib import pyplot as plt
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from scipy.optimize import curve_fit
from utils.measurement import Measurement
from gui.components import (
    AnalysisRangeMixin,
    SampleSelectMixin,
    ShowProfilesMixin,
    CopyPlotMixin,
    ChildWindowCloseMixin,
    StatsWidget,
    PlotMixin
)
import settings
import numpy as np

analysis_name = "Formation"
analysis_types = ["MD", "CD"]

class AnalysisController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, measurement: Measurement, window_type="MD"):
        super().__init__()
        self.measurement = measurement
        self.window_type = window_type
        self.warning_message = None
        self.can_calculate = self.check_required_channels()

        if self.window_type == "MD":
            self.max_dist = np.max(self.measurement.distances)
            self.distances = self.measurement.distances
            self.analysis_range_low = settings.MD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist
            self.analysis_range_high = settings.MD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist

        elif self.window_type == "CD":
            self.max_dist = np.max(self.measurement.cd_distances)
            self.distances = self.measurement.cd_distances
            self.analysis_range_low = settings.CD_FORMATION_RANGE_LOW_DEFAULT * self.max_dist
            self.analysis_range_high = settings.CD_FORMATION_RANGE_HIGH_DEFAULT * self.max_dist

            self.selected_samples = self.measurement.selected_samples.copy()
            self.sampleSelectorWindow = None

        self.show_profiles = False

    def check_required_channels(self):
        """Check if all required channels exist and show alert if not."""
        required_channels = {
            'BW': settings.FORMATION_BW_CHANNEL,
            'Transmission': settings.FORMATION_TRANSMISSION_CHANNEL
        }

        missing_channels = []
        for channel_type, channel_name in required_channels.items():
            if channel_name not in self.measurement.channels:
                missing_channels.append(f"{channel_type} ({channel_name})")

        if missing_channels:
            self.warning_message = f"Required channels not found: {', '.join(missing_channels)}"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("Formation Index Calculation Not Available")
            msg.setInformativeText(self.warning_message)
            msg.setWindowTitle("Missing Channels")
            msg.exec()
            return False

        self.channel = settings.FORMATION_BW_CHANNEL
        self.transmission_channel = settings.FORMATION_TRANSMISSION_CHANNEL
        self.bw_channel = settings.FORMATION_BW_CHANNEL
        return True

    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

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
            unfiltered_data = self.measurement.channel_df[self.channel][low_index:high_index]

            transmission_data = self.measurement.channel_df[self.transmission_channel][low_index:high_index]

            bw_data = self.measurement.channel_df[self.bw_channel][low_index:high_index]

            def linear(x, a, b):
                return a * x + b
            params, covariance = curve_fit(
                linear, transmission_data, bw_data)

            def f(x):
                return linear(x, *params)

            vectorized_function = np.vectorize(f)
            estimated_bw = vectorized_function(transmission_data)

            correlation_matrix = np.corrcoef(bw_data, estimated_bw)
            self.correlation_coefficient = correlation_matrix[0, 1]
            print("Correlation Coefficient:", self.correlation_coefficient)

            y = self.calculate_formation_index(estimated_bw)

        elif self.window_type == "CD":
            low_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_low)
            high_index = np.searchsorted(
                self.measurement.cd_distances, self.analysis_range_high, side='right')

            x = self.measurement.cd_distances[low_index:high_index]

            transmission_data = [self.measurement.segments[self.transmission_channel]
                                 [sample_idx][low_index:high_index] for sample_idx in self.selected_samples]

            transmission_mean_profile = np.mean(transmission_data, axis=0)
            bw_mean_profile = np.mean([self.measurement.segments[self.bw_channel][sample_idx]
                                       [low_index:high_index] for sample_idx in self.selected_samples], axis=0)

            def linear(x, a, b):
                return a * x + b
            params, covariance = curve_fit(
                linear, transmission_mean_profile, bw_mean_profile)

            def f(x):
                return linear(x, *params)

            vectorized_function = np.vectorize(f)
            estimated_bw_profiles = [
                vectorized_function(i) for i in transmission_data]

            correlation_matrix = np.corrcoef(
                bw_mean_profile, np.mean(estimated_bw_profiles, axis=0))
            self.correlation_coefficient = correlation_matrix[0, 1]
            print("Correlation Coefficient:", self.correlation_coefficient)
            formation_profiles = [self.calculate_formation_index(estimated_bw)
                                  for estimated_bw in estimated_bw_profiles]

            y = np.mean(formation_profiles, axis=0)

            if self.show_profiles:
                for i in formation_profiles:
                    ax.plot(x[settings.FORMATION_WINDOW_SIZE-1:],
                            i, color="gray", alpha=0.5, lw=0.5)

        x = x[settings.FORMATION_WINDOW_SIZE-1:]

        show_unfiltered_data = True
        ax.plot(x, y)
        ax.set_title(
            f"{self.measurement.measurement_label} - Formation index ({self.channel})")

        ax.set_xlabel("Distance [m]")
        params = {'mathtext.default': 'regular'}
        plt.rcParams.update(params)
        ax.set_ylabel(f"$f_N$")
        ax.grid()
        self.stats = y

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        mean = np.mean(self.stats)
        std = np.std(self.stats)
        min_val = np.min(self.stats)
        max_val = np.max(self.stats)
        units = self.measurement.units[self.channel]

        stats.append(["Correlation coefficient:",
                     f"{self.correlation_coefficient:.2f}"])
        stats.append(["", f"{self.channel} [{units}]"])
        stats.append([
            "Mean:\nStdev:\nMin:\nMax:",
            f"{mean:.2f}\n{std:.2f}\n{min_val:.2f}\n{max_val:.2f}"
        ])

        return stats

    def calculate_formation_index(self, arr, window_size=settings.FORMATION_WINDOW_SIZE):
        arr = np.array(arr)
        num_values = len(arr) - window_size + 1
        result = np.empty(num_values)

        for i in range(num_values):
            window = arr[i:i + window_size]
            variance = np.var(window)
            sqrt_mean = np.sqrt(np.mean(window))
            result[i] = variance / sqrt_mean if sqrt_mean != 0 else 0

        return result


class AnalysisWindow(QWidget, AnalysisRangeMixin, SampleSelectMixin, ShowProfilesMixin, CopyPlotMixin, ChildWindowCloseMixin):
    def __init__(self, window_type="MD", controller: AnalysisController | None = None, measurement: Measurement | None = None):
        super().__init__()
        self.controller = controller if controller else AnalysisController(
            measurement, window_type)
        self.measurement = self.controller.measurement
        if not self.controller.can_calculate:
            self.close()
            return
        self.window_type = window_type
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        viewMenu = menuBar.addMenu('View')
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(
            self.toggleSelectSamples)

    def initUI(self):
        if settings.FORMATION_TITLE_SHOW:
            self.setWindowTitle(
                f"Formation analysis ({self.measurement.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        if self.window_type == "CD":
            self.initMenuBar(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        if self.window_type == "CD":
            self.addShowProfilesCheckbox(mainLayout)

        # Add description label
        self.textLabel = QLabel(
            "Formation index (calculated from transmission correlated to BW)")
        self.textLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        mainLayout.addWidget(self.textLabel)

        # Add correlation coefficient label
        self.correlationLabel = QLabel("Correlation coefficient: ")
        self.correlationLabel.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        mainLayout.addWidget(self.correlationLabel)

        # Add statistics widget
        self.stats_widget = StatsWidget()
        mainLayout.addWidget(self.stats_widget)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        if self.window_type == "CD":
            self.initShowProfilesCheckbox(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.correlationLabel.setText(
            f"Correlation coefficient: {self.controller.correlation_coefficient:.2f}")
        self.stats_widget.update_statistics(self.controller.stats, "")
