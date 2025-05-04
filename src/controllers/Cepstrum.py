from utils.data_loader import DataMixin
from gui.components import ExportMixin, PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import matplotlib.pyplot as plt
from scipy.signal import welch
import settings
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator, LogLocator, AutoLocator


from scipy.signal import find_peaks
from matplotlib.patches import Rectangle
import matplotlib.legend as mlegend

import matplotlib.patches as mpatches


def tabular_legend(ax, col_labels, data, *args, **kwargs):
    """
    Custom legend function
    Parameters:
    - ax : matplotlib.axes.Axes
    - col_labels : list of column labels
    - data : list of lists containing the values for each legend entry
    """
    # Get current legend handles
    handles, _ = ax.get_legend_handles_labels()

    # Create a blank patch for column labels (no handle)
    blank_patch = mpatches.Rectangle(
        (0, 0), 1, 1, fc="w", edgecolor="none", linewidth=0
    )

    all_rows = [col_labels] + data  # Ensure headers are considered

    # Determine column widths based on the widest element per column
    col_widths = [max(len(str(item)) for item in col)
                  for col in zip(*all_rows)]

    # Format each row with proper spacing
    formatted_rows = [
        "  ".join(str(item).rjust(width)
                  for item, width in zip(row, col_widths))
        for row in all_rows  # Include column labels here
    ]

    # for i in formatted_rows:
    #     print(i)

    # Construct table headers
    # Add blank patch for header alignment
    table_handles = [blank_patch] + handles

    # Create the legend
    legend = ax.legend(
        table_handles,
        formatted_rows,
        prop={'family': 'monospace'},
        loc=kwargs.pop("loc", "upper right"),
        handletextpad=kwargs.pop("handletextpad", 0),
        **kwargs
    )

    return legend


class CepstrumController(QObject, PlotMixin, ExportMixin):
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
                "peak_detection_range_min": settings.MD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.MD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
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
                "peak_detection_range_min": settings.CD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT,
                "peak_detection_range_max": settings.CD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT,
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

        self.peak_detection_range_min = config["peak_detection_range_min"]
        self.peak_detection_range_max = config["peak_detection_range_max"]

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
        self.show_wavelength = settings.SHOW_WAVELENGTH_DEFAULT
        self.auto_detect_peaks = settings.AUTO_DETECT_PEAKS_DEFAULT

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

        # --- CEPSTRUM CALCULATION AND PLOTTING ---
        # Use the extracted data segment for cepstrum calculation
        if self.window_type == "MD":
            data_for_cepstrum = self.data
        else:  # CD
            data_for_cepstrum = np.mean(unfiltered_data, axis=0)

        # Calculate real cepstrum
        spectrum = np.fft.fft(data_for_cepstrum)
        log_spectrum = np.log(np.abs(spectrum) + 1e-12)  # avoid log(0)
        cepstrum = np.fft.ifft(log_spectrum).real

        # Quefrency axis (in meters)
        quefrency = np.arange(len(cepstrum)) * self.dataMixin.sample_step

        # Plot only the first half (up to Nyquist quefrency)
        N = len(cepstrum) // 2
        ax.plot(quefrency[:N], cepstrum[:N])
        ax.set_xlabel("Quefrency [m]")
        ax.set_ylabel("Cepstrum amplitude")

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel}) - Cepstrum")

        ax.grid(True)
        self.canvas.draw()
        self.updated.emit()
        return self.canvas

    def get_freq_in_hz(self, freq_1m):
        return freq_1m * self.machine_speed / 60

    def getStatsTableData(self):
        return None
        stats = []

        # Add headers based on window type
        if self.window_type == "MD":
            stats.append(
                [f"Amplitude {self.dataMixin.units[self.channel]}", "Wavelength [cm]", "Frequency [Hz]", ])
        elif self.window_type == "CD":
            stats.append(["Amplitude", "Wavelength [m]"])

        # Loop over selected frequencies
        for freq in self.selected_freqs:
            if freq:  # Check if the frequency is valid
                wavelength = 1 / freq  # Calculate wavelength from frequency

                # Find the corresponding amplitude
                amplitude_index = np.argmax(self.frequencies == freq)
                amplitude = self.amplitudes[amplitude_index]

                # Add row based on window type
                if self.window_type == "MD":
                    frequency_in_hz = self.get_freq_in_hz(freq)
                    stats.append([
                        f"{amplitude:.2f}",          # Amplitude
                        f"{100 * wavelength:.2f}",  # Wavelength in meters
                        f"{frequency_in_hz:.2f}"   # Frequency in Hz
                    ])
                elif self.window_type == "CD":
                    stats.append([
                        f"{amplitude:.2f}",          # Amplitude
                        f"{100 * wavelength:.2f}"  # Wavelength in meters
                    ])

        return stats

    def getExportData(self):
        data = {
            "Frequency [1/m]": self.frequencies,
            f"{self.channel} amplitude [{self.dataMixin.units[self.channel]}]": self.amplitudes
        }

        return pd.DataFrame(data)
