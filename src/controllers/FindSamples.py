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
        self.band_pass_low  = settings.FIND_SAMPLES_BAND_PASS_LOW_DEFAULT_1M
        self.band_pass_high = settings.FIND_SAMPLES_BAND_PASS_HIGH_DEFAULT_1M
        self.fs = 1 / self.dataMixin.sample_step

    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        self.distances = self.dataMixin.distances
        self.data = self.dataMixin.channel_df[self.channel]

        self.filtered_data = bandpass_filter(
            self.data, self.band_pass_low, self.band_pass_high, self.fs)

        ax.plot(self.distances, self.filtered_data)
        ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"{self.channel} [{self.dataMixin.units[self.channel]}]")

        self.draw_peaks()
        if self.channel == self.dataMixin.peak_channel:
            self.draw_threshold()

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

        peaks = []
        start = None

        tape_width_meters = settings.TAPE_WIDTH_MM / 1000.0
        min_length_meters = settings.CD_SAMPLE_MIN_LENGTH_M

        last_peak_end = None

        for i in range(len(y)):
            if y[i] > self.threshold and start is None:
                start = i
            elif (y[i] <= self.threshold or i == len(y) - 1) and start is not None:
                end = i
                if start is not None and (x[end] - x[start]) >= tape_width_meters:
                    center = x[start] + (x[end] - x[start]) / 2
                    if last_peak_end is None or (x[start] - x[last_peak_end]) >= min_length_meters:
                        peaks.append(center)
                        last_peak_end = end
                    start = None
        self.peaks = peaks

        self.dataMixin.peak_locations = self.peaks
        self.dataMixin.threshold = self.threshold
        self.dataMixin.peak_channel = channel

        return peaks

    def highlight_intervals(self, intervals):
        self.plot()  # Redraw the main plot
        ax = self.figure.gca()

        for start, end in intervals:
            ax.axvspan(start, end, color='black', alpha=0.1)

        self.canvas.draw()

    def zoom_to_interval(self, start, end):
        self.plot()
        ax = self.figure.gca()
        ax.set_xlim(start, end)
        self.canvas.draw()
