from utils.data_loader import DataMixin
from gui.components import ExportMixin, PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import matplotlib.pyplot as plt
from scipy.signal import welch
import settings
import numpy as np
import pandas as pd
from matplotlib.ticker import AutoMinorLocator

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
    print(col_widths)

    # Format each row with proper spacing
    formatted_rows = [
        "  ".join(str(item).rjust(width)
                  for item, width in zip(row, col_widths))
        for row in all_rows  # Include column labels here
    ]
    for i in formatted_rows:
        print(i)

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

        self.peak_detection_range_low = self.max_freq * config["peak_detection_range_min"]
        self.peak_detection_range_high = self.max_freq * config["peak_detection_range_max"]

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

        if settings.SPECTRUM_TITLE_SHOW:
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
                top_peaks = sorted_peak_indices[:
                                                settings.SPECTRUM_AUTO_DETECT_PEAKS]
            else:
                top_peaks = sorted_peak_indices[:1]

            self.selected_freqs = [self.frequencies[peak]
                                   for peak in top_peaks]

        # Draw new lines and update frequency label
        if len(self.selected_freqs) > 0:

            # legend_columns = [f"Amplitude [{self.dataMixin.units[self.channel]}]",
            #                   "Frequency [1/m]", "Wavelength [cm]", "Frequency [Hz]"]
            legend_columns = [f"A [{self.dataMixin.units[self.channel]}]",
                              "F [1/m]", "λ [cm]", "F [Hz]"]

            legend_data = []

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
                        print(f"Spectral peak in {self.channel}: {label}")
                    elif self.window_type == "MD":
                        label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                            100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel]}"
                        print(f"Spectral peak in {self.channel}: {label}")

                        legend_data.append([f"{amplitude:.2f}", f"{selected_freq:.2f}", f"{
                                           100*(1/selected_freq):.2f}", f"{self.get_freq_in_hz(selected_freq):.2f}"])
                        print(f"Spectral peak in {self.channel}: {label}")

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

                    # TODO: DRY, fix this and refactor
                    selected_freq = self.selected_freqs[-1]
                    amplitude = self.amplitudes[np.searchsorted(
                        self.frequencies, selected_freq)]

                    if (i == 1):
                        if self.window_type == "CD":
                            label = f"{selected_freq:.2f} 1/m λ = {100 * 1/selected_freq:.2f} cm A = {
                                amplitude:.2f} {self.dataMixin.units[self.channel]}"
                            print(f"Spectral peak in {self.channel}: {label}")
                        elif self.window_type == "MD":
                            label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                                100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel]}"
                            print(f"Spectral peak in {self.channel}: {label}")
                    else:
                        label = None

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

        if settings.SPECTRUM_SHOW_LEGEND:
            if labels:  # This list will be non-empty if there are items to include in the legend
                if settings.SPECTRUM_LEGEND_OUTSIDE_PLOT:
                    leg = tabular_legend(ax, legend_columns, legend_data, loc="upper left", bbox_to_anchor=(
                        1.05, 1), borderaxespad=0.)

                    leg.get_frame().set_alpha(0)
                else:
                    ax.legend(handles, labels, loc="upper right")

        ax.figure.set_constrained_layout(True)

        if settings.SPECTRUM_MINOR_GRID:
            ax.grid(True, which='both')
            ax.minorticks_on()
            ax.xaxis.set_minor_locator(AutoMinorLocator(5))
            ax.yaxis.set_minor_locator(AutoMinorLocator(4))
            ax.grid(True, which='minor', linestyle=':', linewidth=0.5)
        else:
            ax.grid()

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
