from utils.data_loader import DataMixin
from gui.components import PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import settings
from utils.filters import bandpass_filter


class FindSamplesController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()

        self.threshold = self.dataMixin.threshold
        self.peaks = self.dataMixin.peak_locations
        self.channel = self.dataMixin.peak_channel or self.dataMixin.channels[0]
        self.selected_samples = self.dataMixin.selected_samples
        self.threshold_line = None
        self.peak_lines = []
        self.band_pass_low = settings.FIND_SAMPLES_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high = settings.FIND_SAMPLES_BAND_PASS_HIGH_DEFAULT_1M
        self.fs = 1 / self.dataMixin.sample_step
        self.highlighted_intervals = []
        self.zoomed_in = False
        self.min_length = settings.CD_SAMPLE_MIN_LENGTH_M
        self.max_length = settings.CD_SAMPLE_MAX_LENGTH_M

    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        self.distances = self.dataMixin.distances
        self.data = self.dataMixin.channel_df[self.channel]

        self.filtered_data = bandpass_filter(
            self.data, self.band_pass_low, self.band_pass_high, self.fs)

        alpha = 0.4 if len(self.dataMixin.selected_samples) else 1
        # Draw the entire data line with lower alpha
        ax.plot(self.distances, self.filtered_data,
                color='tab:blue', alpha=alpha)

        # Highlight the selected samples
        for i in self.dataMixin.selected_samples:
            if i < len(self.peaks) - 1:
                start = self.peaks[i]
                end = self.peaks[i + 1]
                mask = (self.distances >= start) & (self.distances <= end)
                ax.plot(
                    self.distances[mask], self.filtered_data[mask], color='tab:blue', alpha=1.0)

        ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"{self.channel} [{self.dataMixin.units[self.channel]}]")

        self.draw_peaks()
        if self.channel == self.dataMixin.peak_channel:
            self.draw_threshold()

        # Highlight selected intervals
        if not self.zoomed_in:
            for start, end in self.highlighted_intervals:
                ax.axvspan(start, end, color='black', alpha=0.1)

        self.zoomed_in = False

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def draw_threshold(self):
        if self.threshold:
            ax = self.figure.gca()
            if self.threshold_line:
                self.threshold_line.remove()
            self.threshold_line = ax.axhline(
                y=self.threshold, color='r', linestyle='--')

    def draw_peaks(self):
        if not self.peaks:
            return
        # Plots the self.peaks
        ax = self.figure.gca()
        self.canvas.draw_idle()

        [i.remove() for i in self.peak_lines]
        self.peak_lines = []

        for peak in self.peaks:
            # Draw the tape edges and the peak center
            vl = ax.axvline(x=peak, color='g', linestyle=':')
            tape_width_m = settings.TAPE_WIDTH_MM / 1000.0

            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak-tape_width_m,
                            color='tab:red', linestyle='--', alpha=0.2)

            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak+tape_width_m,
                            color='tab:red', linestyle='--', alpha=0.2)
            self.peak_lines.append(vl)

    def detect_peaks(self, channel):
        x = self.dataMixin.distances
        y = self.dataMixin.channel_df[channel]

        # TODO: already use the filtered data in the plot method
        y = bandpass_filter(y, self.band_pass_low,
                            self.band_pass_high, self.fs)

        peaks = []
        start = None

        tape_width_meters = settings.TAPE_WIDTH_MM / 1000.0
        min_length_meters = self.min_length
        max_length_meters = self.max_length
        print("min: ", min_length_meters, " max: ", max_length_meters)

        last_peak_end = None

        for i in range(len(y)):
            if y[i] > self.threshold and start is None:
                start = i
            elif (y[i] <= self.threshold or i == len(y) - 1) and start is not None:
                end = i
                if start is not None and (x[end] - x[start]) >= tape_width_meters:
                    center = x[start] + (x[end] - x[start]) / 2

                    # Check if this is the first peak or if the distance from last peak is within bounds
                    if last_peak_end is None or (
                        min_length_meters <= (
                            x[start] - x[last_peak_end]) <= max_length_meters
                    ):
                        peaks.append(center)
                        last_peak_end = end
                    start = None

        self.peaks = peaks
        self.dataMixin.peak_locations = self.peaks
        self.dataMixin.threshold = self.threshold
        self.dataMixin.peak_channel = channel

        return peaks

    def highlight_intervals(self, intervals):
        self.highlighted_intervals = intervals
        self.plot()  # Redraw the main plot

    def zoom_to_interval(self, start, end):
        tape_width_meters = settings.TAPE_WIDTH_MM / 1000.0
        self.zoomed_in = True
        self.plot()
        ax = self.figure.gca()
        ax.set_xlim(start + tape_width_meters / 2, end - tape_width_meters / 2)
        self.canvas.draw()
