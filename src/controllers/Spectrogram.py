from utils.data_loader import DataMixin
from gui.components import PlotMixin
from PyQt6.QtCore import QObject, pyqtSignal
import matplotlib.pyplot as plt
import matplotlib
import settings
import numpy as np

class SpectrogramController(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()

        self.window_type = window_type
        self.ax = None

        # Dynamic initialization based on window type
        spectrum_defaults = {
            "MD": {
                "nperseg": settings.MD_SPECTROGRAM_DEFAULT_LENGTH,
                "range_min": settings.MD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.MD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.MD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.MD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.MD_SPECTROGRAM_OVERLAP,
                "spectrum_length_slider_min": settings.MD_SPECTROGRAM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.MD_SPECTROGRAM_LENGTH_SLIDER_MAX
            },
            "CD": {
                "nperseg": settings.CD_SPECTROGRAM_DEFAULT_LENGTH,
                "range_min": settings.CD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT,
                "range_max": settings.CD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT,
                "analysis_range_low": settings.CD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT,
                "analysis_range_high": settings.CD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT,
                "overlap": settings.CD_SPECTROGRAM_OVERLAP,
                "spectrum_length_slider_min": settings.CD_SPECTROGRAM_LENGTH_SLIDER_MIN,
                "spectrum_length_slider_max": settings.CD_SPECTROGRAM_LENGTH_SLIDER_MAX
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
        self.selected_freq = None
        self.show_wavelength = False

        self.current_hlines = []

    def plot(self):
        self.figure.clear()
        # This to avoid crash due to a too long spectrum calculation on too short data

        self.ax = self.figure.add_subplot(111)
        ax = self.ax

        overlap_per = self.overlap
        noverlap = round(self.nperseg * overlap_per)

        # Extract the segment of data for analysis
        if self.window_type == "MD":
            self.low_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.distances, self.analysis_range_high, side='right')
            self.data = self.dataMixin.channel_df[self.channel][self.low_index:self.high_index]

            if self.nperseg >= (self.high_index-self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return
            data_mean_removed = self.data - np.mean(self.data)

            Pxx, freqs, bins, im = ax.specgram(data_mean_removed,
                                               NFFT=self.nperseg,
                                               Fs=self.fs,
                                               noverlap=noverlap,
                                               window=np.hanning(self.nperseg))

        elif self.window_type == "CD":
            self.low_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_low)
            self.high_index = np.searchsorted(
                self.dataMixin.cd_distances, self.analysis_range_high, side='right')

            if self.nperseg >= (self.high_index-self.low_index):
                self.canvas.draw()
                self.updated.emit()
                return

            x = self.dataMixin.cd_distances[self.low_index:self.high_index]

            unfiltered_data = [self.dataMixin.segments[self.channel][sample_idx]
                               [self.low_index:self.high_index] for sample_idx in self.selected_samples]
            mean_profile = np.mean(unfiltered_data, axis=0)
            mean_profile = mean_profile - np.mean(mean_profile)
            print(mean_profile)


            Pxx, freqs, bins, im = ax.specgram(mean_profile,
                                               NFFT=self.nperseg,
                                               Fs=self.fs,
                                               noverlap=noverlap,
                                               window=np.hanning(self.nperseg))



        amplitudes = np.sqrt(Pxx)
        freq_indices = (freqs >= self.frequency_range_low) & (
            freqs <= self.frequency_range_high)
        freqs_cut = freqs[freq_indices]
        amplitudes_cut = amplitudes[freq_indices, :]
        im = ax.imshow(amplitudes_cut, aspect='auto', origin='lower',
                       extent=[bins[0], bins[-1], freqs_cut[0], freqs_cut[-1]],
                       norm=matplotlib.colors.Normalize(vmin=0, vmax=3*np.mean(amplitudes_cut)), cmap=settings.SPECTROGRAM_COLORMAP)

        # Set the axis labels, title, and colorbar
        ax.set_title(f"{self.dataMixin.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel("Frequency [1/m]")
        cbar = self.figure.colorbar(im, ax=ax, pad=0.2)
        cbar.set_label(f"Amplitude [{self.dataMixin.units[self.channel]}]")

        secax = ax.twinx()

        if self.window_type == "CD" or self.show_wavelength:
            def update_secax(*args):
                primary_ticks = ax.get_yticks()
                secax.set_yticks(primary_ticks)
                secax.set_ylim(*ax.get_ylim())
                secondary_ticks = [100*(1 / i) for i in secax.get_yticks()]
                secax.set_yticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])
            secax.set_ylabel(f"Wavelength [cm]")

        elif self.window_type == "MD":
            def update_secax(*args):
                primary_ticks = ax.get_yticks()
                secax.set_yticks(primary_ticks)
                secax.set_ylim(*ax.get_ylim())
                secondary_ticks = secax.get_yticks() * self.machine_speed / 60
                secax.set_yticklabels(
                    [f"{tick:.2f}" for tick in secondary_ticks])
            secax.set_ylabel(
                f"Frequency [Hz] at machine speed {self.machine_speed:.1f} m/min")

        ax.set_zorder(secax.get_zorder() + 1)
        update_secax()  # Initial call to update secondary axis

        # Update secondary axis on primary axis changes
        ax.callbacks.connect('xlim_changed', update_secax)
        ax.figure.canvas.mpl_connect('resize_event', update_secax)

        # Draw new lines and update frequency label
        if self.selected_freq:

            ylim = ax.get_ylim()

            for i in range(1, settings.MAX_HARMONICS):
                if (self.selected_freq * i > ylim[1]) or (self.selected_freq * i < ylim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue

                label = "Selected frequency" if (i == 1) else None
                hl = ax.axhline(y=self.selected_freq * i,
                                color='r', linestyle='--', alpha=1 - (1/settings.MAX_HARMONICS) * i, label=label)
                self.current_hlines.append(hl)

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

        for index, element in enumerate(self.selected_elements):
            ylim = ax.get_ylim()
            for i in range(1, settings.MAX_HARMONICS):
                f = element["spatial_frequency"]
                if (f * i > ylim[1]) or (f * i < ylim[0]):
                    # Skip drawing the line if it is out of bounds
                    continue
                label = element["name"] if (i == 1) else None
                color_index = index % len(colors)
                current_color = colors[color_index]

                hlw = ax.axhline(y=f * i, color='white', linestyle='-',
                                 alpha=0.8*(1-i*1/settings.MAX_HARMONICS))
                self.current_hlines.append(hlw)

                hl=ax.axhline(y=f * i, linestyle='--', alpha=1 -
                                (1/settings.MAX_HARMONICS) * i, label=label, color=current_color)
                self.current_hlines.append(hl)
        handles, labels=ax.get_legend_handles_labels()
        if labels:  # This list will be non-empty if there are items to include in the legend
            ax.legend(handles, labels, loc="upper right")

        # ax.figure.set_constrained_layout(True)
        # ax.grid()
        # ax.tight_layout()

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def getStatsTableData(self):
        stats = []
        if self.selected_freq:
            wavelength = 1 / self.selected_freq
            stats.append(["Selected frequency:", ""])
            if self.window_type == "MD":
                frequency_in_hz = self.selected_freq * self.machine_speed / 60
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freq:.2f} 1/m ({frequency_in_hz:.2f} Hz)\n{100*wavelength:.2f} m"])
            elif self.window_type == "CD":
                stats.append([
                    "Frequency:\nWavelength:",
                    f"{self.selected_freq:.2f} 1/m\n{100*wavelength:.3f} m"
                ])
        return stats
