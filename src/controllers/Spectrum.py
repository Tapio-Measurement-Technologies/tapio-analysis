from utils.data_loader import DataMixin
from gui.components import ExportMixin, PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import matplotlib.pyplot as plt
from scipy.signal import welch, get_window
import settings
import numpy as np
import pandas as pd
from utils.signal_processing import get_n_peaks

from scipy.signal import find_peaks


class SpectrumController(QObject, PlotMixin, ExportMixin):
    updated = pyqtSignal()

    def __init__(self, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()

        self.window_type = window_type
        self.ax = None

        # Dynamic initialization based on window type
        spectrum_defaults = {
            "MD": {
                "nperseg": settings.MD_SPECTRUM_DEFAULT_LENGTH,
                "range_min": settings.MD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.MD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.MD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.MD_SPECTRUM_OVERLAP,
                "spectrum_length_slider_min": settings.MD_SPECTRUM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.MD_SPECTRUM_LENGTH_SLIDER_MAX
            },
            "CD": {
                "nperseg": settings.CD_SPECTRUM_DEFAULT_LENGTH,
                "range_min": settings.CD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.CD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.CD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.CD_SPECTRUM_OVERLAP,
                "spectrum_length_slider_min": settings.CD_SPECTRUM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.CD_SPECTRUM_LENGTH_SLIDER_MAX
            }
        }

        self.fs = 1 / self.dataMixin.sample_step
        config = spectrum_defaults[self.window_type]
        self.nperseg = config["nperseg"]
        self.overlap = config["overlap"]
        self.max_freq = self.fs / 2
        self.frequency_range_low = self.max_freq * config["range_min"]
        self.frequency_range_high = self.max_freq * config["range_max"]
        self.spectrum_length_slider_min = config["spectrum_length_slider_min"]
        self.spectrum_length_slider_max = config["spectrum_length_slider_max"]

        self.max_dist = np.max(
            self.dataMixin.cd_distances if self.window_type == "CD" else self.dataMixin.distances)

        self.analysis_range_low = config["analysis_range_low"] * self.max_dist
        self.analysis_range_high = config["analysis_range_high"] * \
            self.max_dist

        self.channel = self.dataMixin.channels[0]
        self.machine_speed = settings.PAPER_MACHINE_SPEED_DEFAULT

        self.selected_elements = []
        self.selected_samples = self.dataMixin.selected_samples.copy()
        self.selected_freqs = []
        self.show_wavelength = False
        self.auto_detect_peaks = False

        self.current_vlines = []

        self.spectral_window = settings.SPECTRUM_WELCH_WINDOW

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax

        overlap_per = self.overlap
        noverlap = round(self.nperseg) * overlap_per

        # Extract the segment of data for analysis
        if self.window_type == "MD":
            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel)
            self.low_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_high, side='right')
            self.data = self.dataMixin.channel_df[self.channel][self.low_index:self.high_index]

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            f, Pxx = welch(self.data,
                           fs=self.fs,
                           window=self.spectral_window,
                           nperseg=self.nperseg,
                           noverlap=noverlap,
                           scaling='spectrum')

        elif self.window_type == "CD":

            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel)

            self.low_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_high, side='right')

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            x = self.dataMixin.cd_distances[self.low_index:self.high_index]

            unfiltered_data = [
                self.dataMixin.segments[self.channel][sample_idx][self.low_index:self.high_index]
                for sample_idx in self.selected_samples
            ]

            # Calculate individual power spectra, then use the mean. This to prevent opposite phases canceling each other.
            welches = np.array([
                welch(y, fs=self.fs, window='hann', nperseg=self.nperseg,
                      noverlap=noverlap, scaling='spectrum')
                for y in unfiltered_data
            ])
            f = welches[0][0]
            Pxx = np.mean(welches[:, 1], axis=0)

        f_low_index = np.searchsorted(f, self.frequency_range_low)
        f_high_index = np.searchsorted(
            f, self.frequency_range_high, side='right')
        # Convert power spectral density to amplitude spectrum (sqrt of power)
        amplitude_spectrum = np.sqrt(
            Pxx*2) * settings.SPECTRUM_AMPLITUDE_SCALING

        if self.ax:
            xlim = self.ax.get_xlim()
        else:
            xlim = None

        # Plot the amplitude spectrum

        self.frequencies = f[f_low_index:f_high_index]
        self.amplitudes = amplitude_spectrum[f_low_index:f_high_index]

        ax.plot(self.frequencies, self.amplitudes)
        ax.set_title(f"{self.dataMixin.measurement_label} ({
                     self.channel}) - Spectrum")
        ax.set_xlabel("Frequency [1/m]")
        ax.set_ylabel(f"Amplitude [{self.dataMixin.units[self.channel]}]")
        if ylim:
            ax.set_ylim(bottom=ylim[0], top=ylim[1])

        secax = ax.twiny()

        if self.window_type == "CD" or self.show_wavelength:

            def update_secax(*args):
                primary_ticks = ax.get_xticks()
                secax.set_xticks(primary_ticks)
                secax.set_xlim(*ax.get_xlim())
                secondary_ticks = [100 * (1 / i) for i in secax.get_xticks()]
                secax.set_xticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])

            secax.set_xlabel(f"Wavelength [cm]")

        elif self.window_type == "MD":

            def update_secax(*args):
                primary_ticks = ax.get_xticks()
                secax.set_xticks(primary_ticks)
                secax.set_xlim(*ax.get_xlim())
                secondary_ticks = secax.get_xticks() * self.machine_speed / 60
                secax.set_xticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])

            secax.set_xlabel(f"Frequency [Hz] at machine speed {
                             self.machine_speed:.1f} m/min")

        ax.set_zorder(secax.get_zorder() + 1)
        update_secax()  # Initial call to update secondary axis

        # Update secondary axis on primary axis changes
        ax.callbacks.connect('xlim_changed', update_secax)
        ax.figure.canvas.mpl_connect('resize_event', update_secax)

        if self.auto_detect_peaks:
            peaks, properties = find_peaks(self.amplitudes)
            sorted_peak_indices = peaks[np.argsort(
                self.amplitudes[peaks])][::-1]

            if settings.MULTIPLE_SELECT_MODE:
                top_peaks = sorted_peak_indices[:settings.SPECTRUM_AUTO_DETECT_PEAKS]
            else:
                top_peaks = sorted_peak_indices[:1]

            self.selected_freqs = [self.frequencies[peak]
                                   for peak in top_peaks]

        # Draw new lines and update frequency label
        if len(self.selected_freqs) > 0:

            xlim = ax.get_xlim()
            if settings.MULTIPLE_SELECT_MODE:

                for i, selected_freq in enumerate(self.selected_freqs):

                    if (selected_freq > xlim[1]) or (selected_freq < xlim[0]):
                        continue

                    amplitude = self.amplitudes[np.searchsorted(
                        self.frequencies, selected_freq)]

                    if self.window_type == "CD":
                        label = f"{selected_freq:.2f} 1/m λ = {100 *
                                                               1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel]}"
                    elif self.window_type == "MD":
                        label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                            100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel]}"

                    def get_color_cycler(num_colors):
                        # You can change 'tab10' to any colormap you prefer
                        cmap = plt.get_cmap('tab10')
                        colors = [cmap(i) for i in range(num_colors)]
                        return colors

                    num_lines = len(self.selected_freqs)
                    color_cycle = get_color_cycler(num_lines)

                    vl = ax.axvline(x=selected_freq,
                                    linestyle='--',
                                    alpha=0.5,
                                    color=color_cycle[i % num_lines],
                                    label=label)
                    self.current_vlines.append(vl)

            else:
                for i in range(1, settings.MAX_HARMONICS):
                    if (self.selected_freqs[-1] * i > xlim[1]) or (self.selected_freqs[-1] * i < xlim[0]):
                        # Skip drawing the line if it is out of bounds
                        continue

                    label = "Selected frequency" if (i == 1) else None
                    vl = ax.axvline(x=self.selected_freqs[-1] * i,
                                    color='r',
                                    linestyle='--',
                                    alpha=1 - (1 / settings.MAX_HARMONICS) * i,
                                    label=label)
                    self.current_vlines.append(vl)

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        for index, element in enumerate(self.selected_elements):
            xlim = ax.get_xlim()
            for i in range(1, settings.MAX_HARMONICS):
                f = element["spatial_frequency"]
                if (f * i > xlim[1]) or (f * i < xlim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue
                label = element["name"] if (i == 1) else None
                color_index = index % len(colors)
                current_color = colors[color_index]

                vl = ax.axvline(x=f * i,
                                linestyle='--',
                                alpha=1 - (1 / settings.MAX_HARMONICS) * i,
                                label=label,
                                color=current_color)
                self.current_vlines.append(vl)
        handles, labels = ax.get_legend_handles_labels()
        if labels:  # This list will be non-empty if there are items to include in the legend
            ax.legend(handles, labels, loc="upper right")

        ax.figure.set_constrained_layout(True)
        ax.grid()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def get_freq_in_hz(self, freq_1m):
        return freq_1m * self.machine_speed / 60

    def getStatsTableData(self):
        stats = []
        if len(self.selected_freqs) > 0 and self.selected_freqs[-1]:
            wavelength = 1 / self.selected_freqs[-1]
            stats.append(["Selected frequency:", ""])
            if self.window_type == "MD":
                frequency_in_hz = self.get_freq_in_hz(self.selected_freqs[-1])
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freqs[-1]:.2f} 1/m ({frequency_in_hz:.2f} Hz)\n{100*wavelength:.2f} m"])
            elif self.window_type == "CD":
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freqs[-1]:.2f} 1/m\n{100*wavelength:.3f} m"
                ])
        peaks = get_n_peaks(np.column_stack(
            (self.frequencies, self.amplitudes)), 5)
        frequencies = [f"{freq:.2f}" for freq in peaks[:, 0]]
        amplitudes = [f"{amp:.2f}" for amp in peaks[:, 1]]
        stats.append(["Main periodic components:", ""])
        stats.append(
            ["Frequency [Hz]", f"RMS [{self.dataMixin.units[self.channel]}]"])
        stats.append([
            "\n".join(frequencies),
            "\n".join(amplitudes)
        ])
        return stats

    def getExportData(self):
        data = {
            "Frequency [1/m]": self.frequencies,
            f"{self.channel} amplitude [{self.dataMixin.units[self.channel]}]": self.amplitudes
        }

        return pd.DataFrame(data)
