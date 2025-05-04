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
        self.selected_quefrencies = []
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

        # Welch calculation (same as Spectrum)
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

            unfiltered_data = [
                self.dataMixin.segments[self.channel][sample_idx][self.low_index:self.high_index]
                for sample_idx in self.selected_samples
            ]
            welches = np.array([
                welch(y, fs=self.fs, window='hann', nperseg=self.nperseg,
                      noverlap=noverlap, scaling='spectrum')
                for y in unfiltered_data
            ])
            f = welches[0][0]
            Pxx = np.mean(welches[:, 1], axis=0)

        # --- CEPSTRUM CALCULATION ---
        # Use the amplitude spectrum as in Spectrum
        amplitude_spectrum = np.sqrt(Pxx*2) * settings.SPECTRUM_AMPLITUDE_SCALING

        # Take log and IFFT to get cepstrum
        log_amp = np.log(amplitude_spectrum + 1e-12)
        cepstrum = np.fft.ifft(log_amp).real

        # Quefrency axis (in meters)
        quefrency = np.arange(len(cepstrum)) / self.fs

        # Use the same range selection logic, but for quefrency
        q_low_index = np.searchsorted(quefrency, self.frequency_range_low)
        q_high_index = np.searchsorted(quefrency, self.frequency_range_high, side='right')

        self.frequencies = quefrency[q_low_index:q_high_index]  # Now quefrency!
        self.amplitudes = cepstrum[q_low_index:q_high_index]    # Now cepstrum value!

        ax.plot(self.frequencies, self.amplitudes)
        if settings.SPECTRUM_LOGARITHMIC_SCALE:
            ax.set_yscale("log")
            ax.yaxis.set_major_locator(LogLocator(
                base=10.0, subs=np.arange(1.0, 10.0) * 0.1, numticks=10))

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel}) - Cepstrum")

        ax.set_xlabel("Quefrency [m]")
        ax.set_ylabel(f"Cepstrum [{self.dataMixin.units[self.channel]}]")
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
            # Detect peaks in the cepstrum within the selected quefrency range
            peaks, properties = find_peaks(self.amplitudes)
            sorted_peak_indices = peaks[np.argsort(self.amplitudes[peaks])][::-1]
            visible_peaks = [idx for idx in sorted_peak_indices
                             if q_low_index <= idx < q_high_index]
            if settings.MULTIPLE_SELECT_MODE:
                top_peaks = visible_peaks[:settings.SPECTRUM_AUTO_DETECT_PEAKS]
            else:
                top_peaks = visible_peaks[:1]
            self.selected_quefrencies = [self.frequencies[peak] for peak in top_peaks]
        else:
            self.selected_quefrencies = []

        # Draw vertical lines at detected quefrency peaks
        if len(self.selected_quefrencies) > 0:
            for i, selected_q in enumerate(self.selected_quefrencies):
                amplitude = self.amplitudes[np.searchsorted(self.frequencies, selected_q)]
                label = f"Quefrency: {selected_q:.2f} m, Cepstrum: {amplitude:.2f}"
                ax.axvline(x=selected_q, linestyle='--', alpha=0.5, color='r', label=label)
                self.current_vlines.append(ax)

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
                                alpha=1 -
                                (1 / settings.MAX_HARMONICS_DISPLAY) * i,
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
        stats = []

        # Add headers based on window type
        if self.window_type == "MD":
            stats.append(
                [f"Cepstrum {self.dataMixin.units[self.channel]}", "Quefrency [m]", "Wavelength [cm]", "Frequency [Hz]"])
        elif self.window_type == "CD":
            stats.append(["Cepstrum", "Quefrency [m]", "Wavelength [cm]"])

        # Loop over selected quefrencies
        for q in getattr(self, "selected_quefrencies", []):
            if q:  # Check if the quefrency is valid
                wavelength = q  # In cepstrum, quefrency is already in meters
                # Find the corresponding cepstrum value
                idx = np.searchsorted(self.frequencies, q)
                cepstrum_val = self.amplitudes[idx]
                if self.window_type == "MD":
                    freq_hz = 1 / q * self.machine_speed / 60 if q != 0 else 0
                    stats.append([
                        f"{cepstrum_val:.2f}",  # Cepstrum
                        f"{q:.2f}",            # Quefrency in meters
                        f"{100 * q:.2f}",      # Wavelength in cm
                        f"{freq_hz:.2f}"       # Frequency in Hz
                    ])
                elif self.window_type == "CD":
                    stats.append([
                        f"{cepstrum_val:.2f}",  # Cepstrum
                        f"{q:.2f}",             # Quefrency in meters
                        f"{100 * q:.2f}"        # Wavelength in cm
                    ])

        return stats

    def getExportData(self):
        data = {
            "Quefrency [m]": self.frequencies,
            f"{self.channel} Cepstrum [{self.dataMixin.units[self.channel]}]": self.amplitudes
        }
        return pd.DataFrame(data)
