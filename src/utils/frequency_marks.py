"""Selected frequencies, their harmonics and the paper machine elements, drawn
the same way in every spectral window.

The Spectrum, Cepstrum, Coherence and Spectrogram windows all mark frequencies
on a plot: the ones the user selected (or peak detection found), the harmonics
of each, and the elements checked in the Paper machine data window. This mixin
holds the one implementation of that, so that the windows differ only in what
they must: which axis carries the frequency, what the amplitude is called, and
where a harmonic sits (the cepstrum's rahmonics run the other way).

A controller using it supplies ``frequencies`` and ``amplitudes`` arrays after
plotting, ``mark_amplitude_at(freq)``, and calls ``set_mark_defaults()`` in
its constructor.
"""

import logging

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np

import settings
from utils.plot_formatting import hz_suffix, machine_speed_is_known
from utils.signal_processing import significant_peaks


class FrequencyMarksMixin:
    #: The axis that carries the frequency: "x" for a spectral curve, "y" for
    #: the spectrogram image.
    marks_axis = "x"
    #: The letter the amplitude reading is written with in labels.
    amplitude_symbol = "A"
    #: Whether an element's harmonics are drawn. A whole harmonic family
    #: collapses to one cepstrum peak, so the cepstrum draws none.
    element_harmonics = True
    #: An opaque line drawn beneath every mark, for marks over an image.
    mark_underlay = False

    def set_mark_defaults(self):
        self.set_default('selected_elements', [])
        self.set_default('selected_freqs', [])
        self.set_default('auto_detect_peaks', settings.AUTO_DETECT_PEAKS_DEFAULT)
        self.set_default('show_frequency_in_hz',
                         settings.SHOW_FREQUENCY_IN_HZ_DEFAULT)
        self.set_default('multiple_select', settings.MULTIPLE_SELECT_MODE)
        self.set_default('show_harmonics',
                         settings.SPECTRUM_SHOW_HARMONICS_DEFAULT)
        self.set_default('harmonics_count', settings.MAX_HARMONICS_DISPLAY)
        self.set_default('subharmonic_divisor',
                         settings.SUBHARMONIC_SEARCH_DEFAULT)
        self.current_vlines = []
        self.legend_data = []

    def reset_marks(self):
        """Forget the marks of the previous plot; call it when the figure is cleared."""
        self.current_vlines = []
        self.legend_data = []

    # ------------------------------------------------------------------
    # What a window supplies
    # ------------------------------------------------------------------
    def mark_amplitude_at(self, freq):
        """The plotted value at a frequency, or None when it is off the curve."""
        raise NotImplementedError

    def amplitude_unit(self):
        return self.measurement.units[self.channel]

    def harmonic_frequency(self, fundamental, order):
        return fundamental * order

    def peak_amplitudes(self):
        """The one-dimensional curve peak detection searches."""
        return self.amplitudes

    def get_freq_in_hz(self, freq_1m):
        """Frequency in Hz, or None when no machine speed has been set."""
        if not machine_speed_is_known(self.machine_speed):
            return None
        return freq_1m * self.machine_speed / 60

    def hz_readings_shown(self):
        """Whether the window writes its frequencies in Hz as well as in 1/m.

        A spatial frequency becomes a machine frequency only through the speed
        the sample ran at, so the reading needs an MD window and a known speed -
        and, on top of both, the reader asking for it with "Show frequencies in
        Hz". The speed spinner starts from a configured default rather than
        from the measurement, so a sample measured off the machine, or one whose
        reel speed was never entered, would otherwise carry a confident looking
        Hz figure it never had.
        """
        return (self.window_type == "MD"
                and bool(self.show_frequency_in_hz)
                and machine_speed_is_known(self.machine_speed))

    def hz_suffix_for(self, freq, template=" ({:.2f} Hz)"):
        """The Hz reading to append to a label, or "" where it is not shown."""
        if not self.hz_readings_shown():
            return ""
        return hz_suffix(freq, self.machine_speed, template)

    def analysed_length(self):
        """The length of data the plot was computed from, in metres."""
        if self.window_type == "CD":
            distances = self.measurement.cd_distances
        else:
            distances = self.measurement.distances
        if len(distances) == 0 or not hasattr(self, "low_index"):
            return 0.0
        low = max(0, min(self.low_index, len(distances) - 1))
        high = max(low, min(self.high_index, len(distances)) - 1)
        return float(distances[high] - distances[low])

    # ------------------------------------------------------------------
    # Harmonics
    # ------------------------------------------------------------------
    def harmonic_orders(self):
        """The multiples of a frequency to mark: 1..N, or the fundamental only."""
        if not self.show_harmonics:
            return [1]
        return list(range(1, 1 + max(1, int(self.harmonics_count))))

    def harmonic_alpha(self, order):
        """Harmonic lines fade with their order so the fundamental stands out.

        Never fully transparent: the last harmonic of a long series is still a
        line the user asked for.
        """
        count = len(self.harmonic_orders())
        if count <= 1:
            return 1.0
        return max(0.25, 1 - (order - 1) / count)

    # ------------------------------------------------------------------
    # Drawing primitives, on whichever axis carries the frequency
    # ------------------------------------------------------------------
    def selection_view(self, ax):
        """The frequency span on screen: the zoom is the peak search range."""
        return ax.get_ylim() if self.marks_axis == "y" else ax.get_xlim()

    def _mark_line(self, ax, position, **kwargs):
        draw = ax.axhline if self.marks_axis == "y" else ax.axvline
        if self.mark_underlay:
            draw(position, color='white', linestyle='-',
                 linewidth=kwargs.get('linewidth', 1.5) + 1.0,
                 alpha=0.8 * kwargs.get('alpha', 1.0), zorder=kwargs.get('zorder', 2))
        line = draw(position, **kwargs)
        self.current_vlines.append(line)
        return line

    def _mark_text(self, ax, position, fraction, text, **kwargs):
        """Text at a frequency, ``fraction`` of the way along the other axis.

        Axes coordinates on that other axis, so the text sits at the same
        height whatever the amplitude scale; clipped, so a mark the user zooms
        past is not drawn out in the figure margins.
        """
        kwargs.setdefault('fontsize', 8)
        kwargs.setdefault('clip_on', True)
        if self.marks_axis == "y":
            txt = ax.text(fraction, position, text,
                          transform=ax.get_yaxis_transform(), **kwargs)
        else:
            txt = ax.text(position, fraction, text,
                          transform=ax.get_xaxis_transform(), **kwargs)
        txt.set_path_effects([
            path_effects.Stroke(linewidth=2, foreground='white'),
            path_effects.Normal()
        ])
        return txt

    def _mark_point(self, ax, position, amplitude, **kwargs):
        if self.marks_axis == "y" or amplitude is None:
            return
        ax.scatter([position], [amplitude], zorder=5, **kwargs)

    def draw_harmonic_number(self, ax, frequency, order):
        if self.marks_axis == "y":
            return self._mark_text(ax, frequency, 0.01, f"{order}",
                                   ha='left', va='bottom',
                                   color="tab:gray", alpha=0.8)
        return self._mark_text(ax, frequency, 0.02, f"{order}",
                               ha='center', va='bottom',
                               color="tab:gray", alpha=0.8)

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------
    def describe_frequency(self, freq, amplitude, name=None, symbols=True):
        """One selected frequency in every unit the window shows.

        ``symbols=False`` spells the wavelength out, for a console that is not
        UTF-8 and would refuse the Greek letter.
        """
        text = f"{freq:.2f} 1/m"
        text += self.hz_suffix_for(freq)
        text += f" {'λ' if symbols else 'lambda'} = {100 / freq:.1f} cm"
        if amplitude is not None:
            unit = self.amplitude_unit()
            text += f" {self.amplitude_symbol} = {amplitude:.2f}"
            if unit:
                text += f" {unit}"
        return f"{name}: {text}" if name else text

    def legend_columns(self):
        unit = self.amplitude_unit()
        amplitude = f"{self.amplitude_symbol} [{unit}]" if unit else self.amplitude_symbol
        columns = [amplitude, "F [1/m]", "λ [cm]"]
        if self.hz_readings_shown():
            columns.append("F [Hz]")
        return columns

    def legend_row(self, freq, amplitude):
        row = [f"{amplitude:.3f}", f"{freq:.2f}", f"{100 / freq:.1f}"]
        if self.hz_readings_shown():
            row.append(f"{self.get_freq_in_hz(freq):.2f}")
        return row

    # ------------------------------------------------------------------
    # Selected frequencies
    # ------------------------------------------------------------------
    def drawn_selected_freqs(self):
        """Every selection in multiple selection mode, else the latest one."""
        freqs = [freq for freq in self.selected_freqs
                 if freq is not None and np.isfinite(freq) and freq > 0]
        if not freqs:
            return []
        return freqs if self.multiple_select else freqs[-1:]

    def drawSelectedFrequencies(self, ax):
        """Mark the selected frequencies, each with its harmonics.

        Single and multiple selection draw the same thing per frequency; they
        differ only in how many frequencies are drawn and in their colours. A
        selection is not snapped here: snapping happens on the click, so the
        sub-bin value produced by Refine survives the redraw.
        """
        freqs = self.drawn_selected_freqs()
        if not freqs:
            return

        view = self.selection_view(ax)
        palette = plt.get_cmap('tab10')
        for index, selected_freq in enumerate(freqs):
            color = palette(index % 10) if self.multiple_select else 'r'
            amplitude = self.mark_amplitude_at(selected_freq)
            if amplitude is None:
                continue

            label = self.describe_frequency(selected_freq, amplitude)
            logging.info("Selected peak in %s: %s", self.channel,
                         self.describe_frequency(selected_freq, amplitude, symbols=False))
            self.legend_data.append(self.legend_row(selected_freq, amplitude))

            for order in self.harmonic_orders():
                harmonic = self.harmonic_frequency(selected_freq, order)
                if (harmonic > view[1]) or (harmonic < view[0]):
                    continue

                alpha = self.harmonic_alpha(order)
                self._mark_line(ax, harmonic, color=color, linestyle='--',
                                alpha=alpha, label=label if order == 1 else None)
                self._mark_point(ax, harmonic, self.mark_amplitude_at(harmonic),
                                 s=12, color=color, alpha=alpha)
                if self.show_harmonics and settings.SPECTRUM_SHOW_HARMONICS_NUMBERS:
                    self.draw_harmonic_number(ax, harmonic, order)

    # ------------------------------------------------------------------
    # Paper machine elements
    # ------------------------------------------------------------------
    def element_groups(self):
        """The checked elements by frequency, coincident ones together.

        A headbox slice and a calender roll can both be at 14.7 cm; drawing
        two lines on top of each other says nothing more than one line with
        both names on it. Returns ``(frequency, [names])`` pairs, ascending.
        """
        tolerance = settings.SPECTRUM_ELEMENT_GROUP_TOLERANCE
        elements = sorted(
            (element for element in self.selected_elements
             if element.get("spatial_frequency")),
            key=lambda element: element["spatial_frequency"])
        groups = []
        for element in elements:
            freq = float(element["spatial_frequency"])
            name = element.get("name", "Element")
            if groups and abs(freq - groups[-1][0]) <= tolerance * freq:
                groups[-1][1].append(name)
            else:
                groups.append((freq, [name]))
        return groups

    def element_label(self, freq, names):
        """What the line of an element says: who it is, and where."""
        text = f"{' / '.join(names)}, λ = {100 / freq:.1f} cm"
        text += self.hz_suffix_for(freq, template=", {:.2f} Hz")
        return text

    def _draw_element_label(self, ax, freq, text):
        if self.marks_axis == "y":
            return self._mark_text(ax, freq, 0.99, text, ha='right', va='bottom',
                                   color=settings.SPECTRUM_ELEMENT_COLOR, zorder=4)
        return self._mark_text(ax, freq, 1.0, f" {text}", rotation=90,
                               va='top', ha='left',
                               color=settings.SPECTRUM_ELEMENT_COLOR, zorder=4)

    def _draw_element_harmonic_number(self, ax, freq, order, alpha):
        color = settings.SPECTRUM_ELEMENT_COLOR
        if self.marks_axis == "y":
            return self._mark_text(ax, freq, 0.99, f"{order}", ha='right',
                                   va='bottom', color=color, alpha=max(alpha, 0.6))
        return self._mark_text(ax, freq, 0.98, f"{order}", ha='center',
                               va='top', color=color, alpha=max(alpha, 0.6))

    def drawPaperMachineElements(self, ax):
        """Mark the elements checked in the Paper machine data window.

        Drawn the way the report figures draw them: a thin dotted line in a
        muted colour, named by a label standing along the top of the plot,
        so the element reads as a reference the spectrum is checked against
        rather than as a curve of its own. The harmonics follow the "Show
        harmonics" controls and fade with their order, numbered at the top
        so they do not collide with the numbers of the selection below.
        """
        groups = self.element_groups()
        if not groups:
            return

        color = settings.SPECTRUM_ELEMENT_COLOR
        view = self.selection_view(ax)
        orders = self.harmonic_orders() if self.element_harmonics else [1]
        for freq, names in groups:
            for order in orders:
                harmonic = freq * order
                if (harmonic > view[1]) or (harmonic < view[0]):
                    continue
                alpha = self.harmonic_alpha(order) if self.element_harmonics else 1.0
                self._mark_line(ax, harmonic, color=color, linewidth=0.7,
                                linestyle=(0, (3, 3)), alpha=alpha, zorder=1)
                if order == 1:
                    self._draw_element_label(ax, harmonic, self.element_label(freq, names))
                elif self.show_harmonics and settings.SPECTRUM_SHOW_HARMONICS_NUMBERS:
                    self._draw_element_harmonic_number(ax, harmonic, order, alpha)

    # ------------------------------------------------------------------
    # Stepping the selection
    # ------------------------------------------------------------------
    def get_nearest_frequency_bin_index(self, freq):
        if freq is None or len(self.frequencies) == 0:
            return None
        return int(np.abs(self.frequencies - freq).argmin())

    def move_selected_frequency_by_bins(self, bin_step):
        """Step the latest selection along the plotted bins."""
        if not self.selected_freqs:
            return False

        current_index = self.get_nearest_frequency_bin_index(self.selected_freqs[-1])
        if current_index is None:
            return False

        new_index = int(np.clip(current_index + bin_step, 0, len(self.frequencies) - 1))
        self.selected_freqs[-1] = float(self.frequencies[new_index])
        return True

    # ------------------------------------------------------------------
    # Peak detection
    # ------------------------------------------------------------------
    def peak_search_floor(self):
        """The lowest frequency worth searching for a peak.

        A periodicity the analysed length has not repeated a handful of times
        is the record's own drift rather than a peak, and the DC bin leaks into
        its first neighbours whatever the window. Both are below this.
        """
        floor = float(getattr(self, "peak_detection_range_min", 0.0))
        length = self.analysed_length()
        if length > 0:
            floor = max(floor, settings.SPECTRUM_PEAK_DETECTION_MIN_CYCLES / length)
        if len(self.frequencies) > 1:
            bin_width = float(abs(self.frequencies[1] - self.frequencies[0]))
            floor = max(floor, 3 * bin_width)
        return floor

    def peak_count(self):
        return settings.SPECTRUM_AUTO_DETECT_PEAKS if self.multiple_select else 1

    def standing_peaks(self, view=None):
        """The peaks of the plotted curve that stand clear of its floor.

        Searched between the peak detection range and, when given, the
        visible ``view`` (a zoomed-in axis narrows the search to what is on
        screen). Strongest first; every one of them in multiple selection
        mode, only the strongest otherwise.
        """
        if len(self.frequencies) == 0:
            return []
        low = self.peak_search_floor()
        high = float(getattr(self, "peak_detection_range_max", np.inf))
        if view is not None:
            low = max(low, float(view[0]))
            high = min(high, float(view[1]))
        return significant_peaks(
            self.frequencies, self.peak_amplitudes(), count=self.peak_count(),
            min_freq=low, max_freq=high,
            threshold=settings.SPECTRUM_PEAK_DETECTION_THRESHOLD,
            floor_bins=settings.SPECTRUM_PEAK_DETECTION_FLOOR_BINS)

    def detectPeaks(self, view=None):
        """Replace the selection with the strongest peaks of the plot."""
        peaks = self.standing_peaks(view)
        if not peaks:
            logging.info("No peak in %s stands clear of the floor in the "
                         "searched range.", self.channel)
        self.selected_freqs = [frequency for frequency, _ in peaks]
        return self.selected_freqs
