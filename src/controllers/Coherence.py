from utils.data_loader import DataMixin
from gui.components import ExportMixin, PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import matplotlib.pyplot as plt
from scipy.signal import welch, coherence
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


class CoherenceController(QObject, PlotMixin, ExportMixin):
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


        self.channels = self.dataMixin.channels
        self.channel1 = self.channels[0]
        self.channel2 = self.channels[0]

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

        if self.window_type == "MD":
            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel1)
            self.low_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_high, side='right')
            data1 = self.dataMixin.channel_df[self.channel1][self.low_index:self.high_index]
            data2 = self.dataMixin.channel_df[self.channel2][self.low_index:self.high_index]

            # Normalize both time series
            data1_norm = (data1 - np.mean(data1)) / np.std(data1)
            data2_norm = (data2 - np.mean(data2)) / np.std(data2)

            # Calculate coherence
            f, Cxy = coherence(
                data1_norm,
                data2_norm,
                fs=self.fs,
                window=self.spectral_window,
                nperseg=self.nperseg,
                noverlap=noverlap
            )
            # ax.plot(f, Cxy)
            ax.set_ylabel("Coherence")

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

        elif self.window_type == "CD":
            ylim = settings.MD_SPECTRUM_FIXED_YLIM.get(self.channel1)

            self.low_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_high, side='right')

            if self.nperseg >= (self.high_index - self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return self.canvas

            x = self.dataMixin.cd_distances[self.low_index:self.high_index]
            sample_idx = self.selected_samples[0]  # or loop/average as needed
            data1 = self.dataMixin.segments[self.channel1][sample_idx][self.low_index:self.high_index]
            data2 = self.dataMixin.segments[self.channel2][sample_idx][self.low_index:self.high_index]

            # Normalize both time series
            data1_norm = (data1 - np.mean(data1)) / np.std(data1)
            data2_norm = (data2 - np.mean(data2)) / np.std(data2)

            # Calculate coherence
            f, Cxy = coherence(
                data1_norm,
                data2_norm,
                fs=self.fs,
                window=self.spectral_window,
                nperseg=self.nperseg,
                noverlap=noverlap
            )
            # ax.plot(f, Cxy)
            ax.set_ylabel("Coherence")

        f_low_index = np.searchsorted(f, self.frequency_range_low)
        f_high_index = np.searchsorted(
            f, self.frequency_range_high, side='right')
        # Convert power spectral density to amplitude spectrum (sqrt of power)
        amplitude_spectrum = Cxy

        if self.ax:
            xlim = self.ax.get_xlim()
        else:
            xlim = None

        # Plot the amplitude spectrum

        self.frequencies = f[f_low_index:f_high_index]
        self.amplitudes = amplitude_spectrum[f_low_index:f_high_index]

        ax.plot(self.frequencies, self.amplitudes)
        if settings.SPECTRUM_LOGARITHMIC_SCALE:
            ax.set_yscale("log")
            ax.yaxis.set_major_locator(LogLocator(
                base=10.0, subs=np.arange(1.0, 10.0) * 0.1, numticks=10))

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.dataMixin.measurement_label} Coherence ({
                self.channel1} vs {self.channel2})")

        ax.set_xlabel("Frequency [1/m]")
        ax.set_ylabel(f"Coherence")
        ax.set_ylim(0, 1)

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

            # First detect peaks in the full spectrum within peak detection range
            pf_low_index = np.searchsorted(f, self.peak_detection_range_min)
            pf_high_index = np.searchsorted(f, self.peak_detection_range_max, side='right')
            
            # Only proceed with peak detection if we have a valid range
            if pf_high_index > pf_low_index:
                # Slice the full amplitude spectrum for peak detection
                amplitude_spectrum_for_peaks = amplitude_spectrum[pf_low_index:pf_high_index]
                
                # Detect peaks in the peak detection range
                peaks, properties = find_peaks(amplitude_spectrum_for_peaks)
                
                # Map peaks back to global frequency indices
                peaks_global = peaks + pf_low_index
                
                # Sort peaks based on their amplitudes
                sorted_peak_indices = peaks_global[np.argsort(amplitude_spectrum[peaks_global])][::-1]
                
                # Filter peaks to only include those within the visible range
                visible_peaks = [idx for idx in sorted_peak_indices 
                               if f_low_index <= idx < f_high_index]
                
                if settings.MULTIPLE_SELECT_MODE:
                    top_peaks = visible_peaks[:settings.SPECTRUM_AUTO_DETECT_PEAKS]
                else:
                    top_peaks = visible_peaks[:1]
                
                # Convert peak indices to frequencies
                self.selected_freqs = [f[peak] for peak in top_peaks]
            else:
                self.selected_freqs = []

        # Draw new lines and update frequency label
        if len(self.selected_freqs) > 0:

            # legend_columns = [f"Amplitude [{self.dataMixin.units[self.channel1]}]",
            #                   "Frequency [1/m]", "Wavelength [cm]", "Frequency [Hz]"]
            if self.window_type == "MD":
                legend_columns = [f"A [{self.dataMixin.units[self.channel1]}]",
                                  "F [1/m]", "λ [cm]", "F [Hz]"]
            if self.window_type == "CD":
                legend_columns = [f"A [{self.dataMixin.units[self.channel1]}]",
                                  "F [1/m]", "λ [cm]"]

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
                                                               1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel1]}"
                        print(f"Spectral peak in {self.channel1}: {label}")
                        legend_data.append([f"{amplitude:.2f}", f"{selected_freq:.2f}", f"{
                                           100*(1/selected_freq):.2f}"])
                    elif self.window_type == "MD":
                        label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                            100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel1]}"
                        print(f"Spectral peak in {self.channel1}: {label}")

                        legend_data.append([f"{amplitude:.3f}", f"{selected_freq:.2f}", f"{
                                           100*(1/selected_freq):.2f}", f"{self.get_freq_in_hz(selected_freq):.2f}"])
                        print(f"Spectral peak in {self.channel1}: {label}")

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
                for i in range(1, settings.MAX_HARMONICS_DISPLAY):
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
                                amplitude:.2f} {self.dataMixin.units[self.channel1]}"
                            print(f"Spectral peak in {self.channel1}: {label}")
                        elif self.window_type == "MD":
                            label = f"{selected_freq:.2f} 1/m ({self.get_freq_in_hz(selected_freq):.2f} Hz) λ = {
                                100 * 1/selected_freq:.2f} cm A = {amplitude:.2f} {self.dataMixin.units[self.channel1]}"
                            print(f"Spectral peak in {self.channel1}: {label}")
                    else:
                        label = None

                    vl = ax.axvline(x=self.selected_freqs[-1] * i,
                                    color='r',
                                    linestyle='--',
                                    alpha=1 - (1 / settings.MAX_HARMONICS_DISPLAY) * i,
                                    label=label)
                    self.current_vlines.append(vl)

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        for index, element in enumerate(self.selected_elements):
            xlim = ax.get_xlim()
            for i in range(1, settings.MAX_HARMONICS_DISPLAY):
                f = element["spatial_frequency"]
                if (f * i > xlim[1]) or (f * i < xlim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue
                label = element["name"] if (i == 1) else None
                color_index = index % len(colors)
                current_color = colors[color_index]

                vl = ax.axvline(x=f * i,
                                linestyle='--',
                                alpha=1 - (1 / settings.MAX_HARMONICS_DISPLAY) * i,
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
                [f"Amplitude {self.dataMixin.units[self.channel1]}", "Wavelength [cm]", "Frequency [Hz]", ])
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
            f"{self.channel1} amplitude [{self.dataMixin.units[self.channel1]}]": self.amplitudes
        }

        return pd.DataFrame(data)
