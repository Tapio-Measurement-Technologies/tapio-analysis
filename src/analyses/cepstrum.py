import logging
from PyQt6.QtWidgets import (QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
                             QGroupBox)
from PyQt6.QtGui import QAction
from gui.components import (
    AnalysisRangeMixin,
    ChannelMixin,
    QuefrencyRangeMixin,
    MachineSpeedMixin,
    SpectrumLengthMixin,
    CopyPlotMixin,
    AutoDetectPeaksMixin,
    ChildWindowCloseMixin,
    ExportMixin,
    ControlsPanelWidget
)
from gui.paper_machine_data import PaperMachineDataWindow
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.signal_processing import safe_spectral_params, interpolate_non_finite
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from scipy.signal import welch, find_peaks
import numpy as np
import pandas as pd
import settings

analysis_name = "Cepstrum"
analysis_types = ["MD"]


class AnalysisController(AnalysisControllerBase, ExportMixin):
    nperseg: float
    overlap: float
    quefrency_range_low: float
    quefrency_range_high: float
    spectrum_length_slider_min: float
    spectrum_length_slider_max: float
    analysis_range_low: float
    analysis_range_high: float
    machine_speed: float
    selected_elements: list[str]
    selected_freqs: list[float]

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)
        self.ax = None

        self.current_vlines = []
        self.spectral_window = settings.SPECTRUM_WELCH_WINDOW

        self.set_default('nperseg', settings.MD_SPECTRUM_DEFAULT_LENGTH)
        self.set_default('overlap', settings.MD_SPECTRUM_OVERLAP)
        self.set_default('spectrum_length_slider_min',
                         settings.MD_SPECTRUM_LENGTH_SLIDER_MIN)
        self.set_default('spectrum_length_slider_max',
                         settings.MD_SPECTRUM_LENGTH_SLIDER_MAX)
        self.set_default('analysis_range_low',
                         settings.MD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT * self.max_dist)
        self.set_default('analysis_range_high',
                         settings.MD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT * self.max_dist)
        self.set_default('quefrency_range_low',
                         min(settings.CEPSTRUM_QUEFRENCY_RANGE_MIN_DEFAULT, self.max_quefrency))
        self.set_default('quefrency_range_high',
                         min(settings.CEPSTRUM_QUEFRENCY_RANGE_MAX_DEFAULT, self.max_quefrency))
        self.set_default('machine_speed', settings.PAPER_MACHINE_SPEED_DEFAULT)
        self.set_default('selected_elements', [])
        self.set_default('selected_freqs', [])
        self.set_default('auto_detect_peaks', settings.AUTO_DETECT_PEAKS_DEFAULT)

    @property
    def quefrency_step(self):
        """Spacing of the cepstrum's x axis, which is the sampling interval.

        The Welch spectrum is one-sided over [0, fs/2], so its inverse transform
        is sampled at 1/fs - the same step as the underlying measurement.
        """
        return 1.0 / self.fs

    @property
    def max_quefrency(self):
        """Longest period the current window length can produce.

        Only the first half of the (symmetric) cepstrum is kept, so the axis
        stops at half a Welch segment.
        """
        return (int(self.nperseg) // 2) * self.quefrency_step

    def _finish_plot(self):
        self.canvas.draw()
        self.updated.emit()
        return self.canvas

    def plot(self):
        self.figure.clear()

        self.ax = self.figure.add_subplot(111)
        ax = self.ax
        self.frequencies = np.array([])
        self.amplitudes = np.array([])
        self.quefrencies = np.array([])
        self.cepstrum_amplitudes = np.array([])
        self.current_vlines = []
        ax.set_xlabel("Quefrency (period) [m]")
        ax.set_ylabel("Cepstrum amplitude")
        ax.grid(True)

        if settings.SPECTRUM_TITLE_SHOW:
            ax.set_title(f"{self.measurement.measurement_label} ({self.channel}) - Cepstrum")

        # Extract the segment of data for analysis
        self.low_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_low)
        self.high_index = np.searchsorted(
            self.measurement.distances, self.analysis_range_high, side='right')
        self.data, _ = interpolate_non_finite(
            self.measurement.channel_df[self.channel][self.low_index:self.high_index],
            context=f"{self.channel} cepstrum")

        spectral_params = safe_spectral_params(
            self.nperseg,
            self.overlap,
            len(self.data),
        )
        if spectral_params is None:
            return self._finish_plot()
        nperseg, noverlap = spectral_params

        # The inverse transform below reconstructs 2*(len(Pxx)-1) samples, which
        # is the segment length only when that length is even. safe_spectral_params
        # returns an odd nperseg whenever it clamps to the data length, and the
        # resulting half-bin mismatch skews the whole quefrency scale.
        nperseg -= nperseg % 2
        noverlap = min(noverlap, nperseg - 1)
        if nperseg < 4:
            return self._finish_plot()

        f, Pxx = welch(self.data,
                       fs=self.fs,
                       window=self.spectral_window,
                       nperseg=nperseg,
                       noverlap=noverlap,
                       scaling='spectrum')

        # --- CEPSTRUM CALCULATION AND PLOTTING ---
        # The cepstrum is taken from the Welch-averaged power spectrum computed
        # above, not from a single FFT of the whole record. A raw periodogram has
        # chi-squared(2) statistics, so log|X| is dominated by estimator noise and
        # the cepstrum of that noise buries the rahmonics - the previous version
        # failed to rank the true period first even on a noise-free harmonic
        # series. Averaging over segments first is what makes the peaks emerge,
        # and it also makes the spectrum length slider control the result.
        if len(Pxx) < 4:
            return self._finish_plot()

        # Clamp the spectrum to a fixed dynamic range below its peak before
        # taking the log. Without this the near-empty bins between harmonics
        # dominate log(P) and their broadband cepstral content buries the
        # rahmonics; with it, the true period ranks first even at high noise.
        power = np.asarray(Pxx, dtype=float).copy()
        peak = power.max()
        if not np.isfinite(peak) or peak <= 0:
            return self._finish_plot()
        floor = peak * 10 ** (-settings.CEPSTRUM_DYNAMIC_RANGE_DB / 10.0)
        power = np.maximum(power, floor)

        # The real cepstrum is defined on the log magnitude spectrum, and Welch
        # returns power, so halve the log rather than doubling every amplitude.
        log_spectrum = 0.5 * np.log(power)
        # Remove the mean of the log spectrum: it only sets cepstrum[0] and would
        # otherwise dwarf every rahmonic on the plot.
        log_spectrum = log_spectrum - np.mean(log_spectrum)

        cepstrum = np.fft.irfft(log_spectrum, n=2 * (len(log_spectrum) - 1))
        quefrency = np.arange(len(cepstrum)) * self.quefrency_step

        # The real cepstrum of a real spectrum is symmetric; keep the first half,
        # then show only the quefrency window the user asked for. Slicing the
        # stored arrays keeps the plot, the peak search, the statistics table and
        # the export all describing the same data.
        half = len(cepstrum) // 2
        quefrency = quefrency[:half]
        cepstrum = cepstrum[:half]

        q_low_index = np.searchsorted(quefrency, self.quefrency_range_low)
        q_high_index = np.searchsorted(
            quefrency, self.quefrency_range_high, side='right')

        self.quefrencies = quefrency[q_low_index:q_high_index]
        self.cepstrum_amplitudes = cepstrum[q_low_index:q_high_index]
        # Aliases: PlotMixin.invalidate_results and the report code address every
        # analysis through frequencies/amplitudes.
        self.frequencies = self.quefrencies
        self.amplitudes = self.cepstrum_amplitudes

        if len(self.quefrencies) == 0:
            return self._finish_plot()

        ax.plot(self.quefrencies, self.cepstrum_amplitudes)

        self.addSecondaryAxis(ax)

        if self.auto_detect_peaks:
            self.detectPeaks()

        self.drawSelectedQuefrency(ax)
        self.drawPaperMachineElements(ax)

        handles, labels = ax.get_legend_handles_labels()
        if settings.SPECTRUM_SHOW_LEGEND and labels:
            if settings.SPECTRUM_LEGEND_OUTSIDE_PLOT:
                # These labels carry four units each, so they are wide enough to
                # cover the plot when they are drawn inside it.
                legend = ax.legend(handles, labels, loc="upper left",
                                   bbox_to_anchor=(1.02, 1), borderaxespad=0.)
                legend.get_frame().set_alpha(0)
            else:
                ax.legend(handles, labels, loc="upper right")

        return self._finish_plot()

    def addSecondaryAxis(self, ax):
        """Label the top axis in Hz, the rotational rate a period corresponds to.

        A quefrency is a wavelength, so the machine-frame frequency is the
        reciprocal scaled by the machine speed. That makes the mapping
        non-linear, so the ticks stay on the primary axis positions and only
        their labels are recomputed - the same approach Spectrum uses.
        """
        secax = ax.twiny()

        def update_secax(*args):
            primary_ticks = ax.get_xticks()
            secax.set_xticks(primary_ticks)
            secax.set_xlim(*ax.get_xlim())
            labels = []
            for tick in secax.get_xticks():
                hz = self.quefrency_to_hz(tick)
                labels.append("" if hz is None else f"{hz:.2f}")
            secax.set_xticklabels(labels)

        secax.set_xlabel("Frequency [Hz]")
        ax.set_zorder(secax.get_zorder() + 1)
        update_secax()

        ax.callbacks.connect('xlim_changed', update_secax)
        ax.figure.canvas.mpl_connect('resize_event', update_secax)

    def detectPeaks(self):
        """Rank the cepstral peaks inside the current quefrency range.

        The arrays are already sliced to that range, so the range slider is the
        search window: it is what keeps the spectral-envelope hump near q=0 from
        winning every time.
        """
        if len(self.cepstrum_amplitudes) < 3:
            self.selected_freqs = []
            return

        peaks, _ = find_peaks(self.cepstrum_amplitudes)
        if len(peaks) == 0:
            self.selected_freqs = []
            return

        ranked = peaks[np.argsort(self.cepstrum_amplitudes[peaks])][::-1]
        if settings.MULTIPLE_SELECT_MODE:
            count = settings.SPECTRUM_AUTO_DETECT_PEAKS or len(ranked)
        else:
            count = 1

        self.selected_freqs = [float(self.quefrencies[peak])
                               for peak in ranked[:count]]

    def drawSelectedQuefrency(self, ax):
        """Mark the selected period and its rahmonics.

        A cepstral peak at q0 repeats at n*q0, the direct analogue of the
        harmonics at n*f0 that Spectrum draws. The selection is deliberately not
        snapped here: snapping happens when the user clicks, so that the sub-bin
        value produced by Refine survives the redraw.
        """
        if not self.selected_freqs:
            return

        q0 = self.selected_freqs[-1]
        if not np.isfinite(q0) or q0 <= 0:
            return

        xlim = ax.get_xlim()
        for i in range(1, 1 + settings.MAX_HARMONICS_DISPLAY):
            rahmonic = q0 * i
            if (rahmonic > xlim[1]) or (rahmonic < xlim[0]):
                continue

            amplitude = self.get_cepstrum_amplitude_at(rahmonic)
            if amplitude is None:
                continue

            if i == 1:
                label = self.describe_quefrency(q0, amplitude)
                logging.info("Cepstral peak in %s: %s", self.channel,
                             self.describe_quefrency(q0, amplitude, symbols=False))
            else:
                label = None

            alpha = 1 - (1 / settings.MAX_HARMONICS_DISPLAY) * i
            vl = ax.axvline(x=rahmonic,
                            color='r',
                            linestyle='--',
                            alpha=alpha,
                            label=label)
            self.current_vlines.append(vl)
            ax.scatter([rahmonic], [amplitude], s=10, color='r',
                       alpha=max(0.25, alpha), zorder=5)

            if settings.SPECTRUM_SHOW_HARMONICS_NUMBERS:
                ymin, ymax = ax.get_ylim()
                txt = ax.text(rahmonic,
                              ymin + 0.02 * (ymax - ymin),
                              f"{i}",
                              ha='center',
                              va='bottom',
                              fontsize=8,
                              color="tab:gray",
                              alpha=0.8)
                txt.set_path_effects([
                    path_effects.Stroke(linewidth=2, foreground='white'),
                    path_effects.Normal()
                ])

    def drawPaperMachineElements(self, ax):
        """Mark the periods of the elements checked in the Paper machine data window."""
        if not self.selected_elements:
            return

        colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
        xlim = ax.get_xlim()

        for index, element in enumerate(self.selected_elements):
            spatial_frequency = element.get("spatial_frequency")
            if not spatial_frequency:
                continue
            # An element that repeats at f 1/m has a period of 1/f metres.
            element_quefrency = 1.0 / spatial_frequency

            for i in range(1, settings.MAX_HARMONICS_DISPLAY):
                rahmonic = element_quefrency * i
                if (rahmonic > xlim[1]) or (rahmonic < xlim[0]):
                    continue

                label = None
                if i == 1:
                    name = element.get("name", "Element")
                    label = f"{name}: {self.describe_quefrency(element_quefrency)}"

                vl = ax.axvline(x=rahmonic,
                                linestyle='--',
                                alpha=1 - (1 / settings.MAX_HARMONICS_DISPLAY) * i,
                                label=label,
                                color=colors[index % len(colors)])
                self.current_vlines.append(vl)

    def get_freq_in_hz(self, freq_1m):
        """Convert a spatial frequency [1/m] to a machine frequency [Hz]."""
        return freq_1m * self.machine_speed / 60

    def quefrency_to_frequency(self, quefrency):
        """Convert a quefrency [m], which is a period, to a frequency [1/m]."""
        if quefrency is None or not np.isfinite(quefrency) or quefrency <= 0:
            return None
        return 1.0 / quefrency

    def quefrency_to_hz(self, quefrency):
        frequency = self.quefrency_to_frequency(quefrency)
        if frequency is None:
            return None
        return self.get_freq_in_hz(frequency)

    def describe_quefrency(self, quefrency, amplitude=None, symbols=True):
        """One-line readout of a period in every unit the user works in.

        symbols=False spells the wavelength out instead of using a lambda. The
        console on Windows is usually cp1252, where printing the symbol raises
        UnicodeEncodeError - and a raise inside plot() is caught upstream and
        shown as "Invalid parameters", losing the whole analysis.
        """
        frequency = self.quefrency_to_frequency(quefrency)
        if frequency is None:
            return "None"

        wavelength = "λ" if symbols else "wavelength"
        text = (f"{quefrency:.4f} m  "
                f"{wavelength} = {100 * quefrency:.2f} cm  "
                f"f = {frequency:.3f} 1/m ({self.get_freq_in_hz(frequency):.2f} Hz)")
        if amplitude is not None:
            text += f"  A = {amplitude:.4g}"
        return text

    def get_nearest_quefrency_bin_index(self, quefrency):
        if quefrency is None or not hasattr(self, "quefrencies") or len(self.quefrencies) == 0:
            return None

        return int(np.abs(self.quefrencies - quefrency).argmin())

    def snap_quefrency_to_bin(self, quefrency):
        bin_index = self.get_nearest_quefrency_bin_index(quefrency)
        if bin_index is None:
            return None

        snapped = float(self.quefrencies[bin_index])
        if snapped <= 0 or not np.isfinite(snapped):
            # A zero period has no frequency, so refuse to select it rather than
            # letting 1/q divide by zero further down.
            return None

        return snapped

    def get_bin_location(self, quefrency):
        bin_index = self.get_nearest_quefrency_bin_index(quefrency)
        if bin_index is None:
            return None, None

        return float(self.quefrencies[bin_index]), float(self.cepstrum_amplitudes[bin_index])

    def get_cepstrum_amplitude_at(self, quefrency):
        if quefrency is None or not hasattr(self, "quefrencies") or len(self.quefrencies) == 0:
            return None

        if quefrency < self.quefrencies[0] or quefrency > self.quefrencies[-1]:
            return None

        return float(np.interp(quefrency, self.quefrencies, self.cepstrum_amplitudes))

    def move_selected_quefrency_by_bins(self, bin_step):
        if not self.selected_freqs:
            return False

        current_index = self.get_nearest_quefrency_bin_index(self.selected_freqs[-1])
        if current_index is None:
            return False

        new_index = int(np.clip(current_index + bin_step, 0, len(self.quefrencies) - 1))
        self.selected_freqs[-1] = float(self.quefrencies[new_index])
        return True

    def refine_selected_quefrency(self):
        """Sub-bin period estimate by fitting a parabola over the selected peak.

        The cepstral peak of a real period almost never lands exactly on a bin,
        and the bin spacing is the measurement's sample step. Interpolating over
        the peak and its two neighbours recovers most of that lost resolution.
        Returns None when the selection sits at an edge or on a flat stretch,
        where the fit has no meaning.
        """
        if not self.selected_freqs:
            return None

        amplitudes = self.cepstrum_amplitudes
        index = self.get_nearest_quefrency_bin_index(self.selected_freqs[-1])
        if index is None or index == 0 or index >= len(amplitudes) - 1:
            return None

        y0, y1, y2 = (float(amplitudes[index - 1]),
                      float(amplitudes[index]),
                      float(amplitudes[index + 1]))
        denominator = y0 - 2 * y1 + y2
        if denominator == 0 or not np.isfinite(denominator):
            return None

        delta = 0.5 * (y0 - y2) / denominator
        if not np.isfinite(delta) or abs(delta) > 1:
            return None

        refined = float(self.quefrencies[index]) + delta * self.quefrency_step
        if not np.isfinite(refined) or refined <= 0:
            return None

        return refined

    def getStatsTableData(self):
        stats = [["Quefrency [m]", "Wavelength [cm]",
                  "Frequency [1/m]", "Frequency [Hz]", "Amplitude"]]

        for quefrency in self.selected_freqs:
            frequency = self.quefrency_to_frequency(quefrency)
            if frequency is None:
                continue

            amplitude = self.get_cepstrum_amplitude_at(quefrency)
            stats.append([
                f"{quefrency:.4f}",
                f"{100 * quefrency:.2f}",
                f"{frequency:.3f}",
                f"{self.get_freq_in_hz(frequency):.2f}",
                "-" if amplitude is None else f"{amplitude:.4g}"
            ])

        return stats

    def getExportData(self):
        quefrencies = np.asarray(self.quefrencies, dtype=float)
        with np.errstate(divide='ignore', invalid='ignore'):
            frequencies = np.where(quefrencies > 0, 1.0 / quefrencies, np.nan)

        data = {
            "Quefrency [m]": quefrencies,
            "Wavelength [cm]": 100 * quefrencies,
            "Frequency [1/m]": frequencies,
            f"{self.channel} cepstrum amplitude": self.cepstrum_amplitudes
        }

        return pd.DataFrame(data)


class AnalysisWindow(AnalysisWindowBase[AnalysisController], AnalysisRangeMixin, ChannelMixin, QuefrencyRangeMixin,
                     MachineSpeedMixin, SpectrumLengthMixin, CopyPlotMixin, AutoDetectPeaksMixin,
                     ChildWindowCloseMixin):

    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.paperMachineDataWindow = None
        self.checked_elements = []
        self.initUI()

    def initMenuBar(self):
        exportAction = self.controller.initExportAction(
            self, "Export cepstrum")
        self.file_menu.addAction(exportAction)

        viewMenu = self.menu_bar.addMenu('View')

        self.paperMachineDataAction = QAction('Paper machine data', self)

        if not self.measurement.pm_data:
            self.paperMachineDataAction.setDisabled(True)
        viewMenu.addAction(self.paperMachineDataAction)

        self.paperMachineDataAction.setCheckable(True)
        self.paperMachineDataAction.triggered.connect(
            self.togglePaperMachineData)

    def togglePaperMachineData(self, checked):
        if self.paperMachineDataWindow is None:
            self.paperMachineDataWindow = PaperMachineDataWindow(
                self.updateElements, self.window_type, self.checked_elements, self.measurement)
            self.paperMachineDataWindow.show()
            self.paperMachineDataWindow.refresh_pm_data(
                self.controller.machine_speed, self.selectedFrequency())
            self.paperMachineDataWindow.closed.connect(
                self.onPaperMachineDataClosed)
            self.paperMachineDataAction.setChecked(True)
        else:
            self.paperMachineDataWindow.close()

    def updateElements(self, selected_elements=None):
        self.checked_elements = selected_elements
        self.controller.selected_elements = selected_elements
        self.refresh()

    def onPaperMachineDataClosed(self):
        self.paperMachineDataWindow = None
        self.paperMachineDataAction.setChecked(False)

    def initUI(self):
        self.setWindowTitle(f"{analysis_name} ({self.controller.window_type}) - {self.measurement.measurement_label}")
        self.resize(*settings.CEPSTRUM_WINDOW_SIZE)

        self.initMenuBar()

        # Main horizontal layout for controls and plot
        mainHorizontalLayout = QHBoxLayout()
        self.main_layout.addLayout(mainHorizontalLayout)

        # Left panel for controls
        self.controlsPanel = ControlsPanelWidget()
        mainHorizontalLayout.addWidget(self.controlsPanel, 0)

        # Data Selection Group
        dataSelectionGroup = QGroupBox("Data Selection")
        dataSelectionLayout = QVBoxLayout()
        dataSelectionGroup.setLayout(dataSelectionLayout)
        self.controlsPanel.addWidget(dataSelectionGroup)
        self.addChannelSelector(dataSelectionLayout)

        # Analysis Parameters Group
        analysisParamsGroup = QGroupBox("Analysis Parameters")
        analysisParamsLayout = QVBoxLayout()
        analysisParamsGroup.setLayout(analysisParamsLayout)
        self.controlsPanel.addWidget(analysisParamsGroup)
        self.addAnalysisRangeSlider(analysisParamsLayout)
        self.addQuefrencyRangeSlider(analysisParamsLayout)
        self.addSpectrumLengthSlider(analysisParamsLayout)
        self.addMachineSpeedSpinner(analysisParamsLayout)

        # Display & Peak Options Group
        displayOptionsGroup = QGroupBox("Display && Peak Options")
        displayOptionsLayout = QVBoxLayout()
        displayOptionsGroup.setLayout(displayOptionsLayout)
        self.controlsPanel.addWidget(displayOptionsGroup)

        self.addAutoDetectPeaksCheckbox(displayOptionsLayout)

        self.refineButton = QPushButton("Refine Quefrency Selection")
        self.refineButton.clicked.connect(self.refineFrequency)
        displayOptionsLayout.addWidget(self.refineButton)

        self.clearButton = QPushButton("Clear Quefrency Selection")
        self.clearButton.clicked.connect(self.clearFrequency)
        displayOptionsLayout.addWidget(self.clearButton)

        # Right panel for plot
        plotLayout = QVBoxLayout()
        mainHorizontalLayout.addLayout(plotLayout, 1)

        self.selectedQuefrencyLabel = QLabel("Selected quefrency: None")
        plotLayout.addWidget(self.selectedQuefrencyLabel)

        # Matplotlib figure and canvas
        self.controller.addPlot(plotLayout)
        self.controller.canvas.mpl_connect('button_press_event', self.onclick)
        self.controller.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.controller.canvas.set_context_menu_actions_provider(
            self.contextMenuActions)

        self.refresh()

    def selectedQuefrency(self):
        selected_freqs = self.controller.selected_freqs
        return selected_freqs[-1] if selected_freqs else None

    def selectedFrequency(self):
        """The selection as a spatial frequency, which is what other views speak."""
        return self.controller.quefrency_to_frequency(self.selectedQuefrency())

    def takeManualControl(self):
        """Stop re-detecting peaks once the user has picked a quefrency.

        Detection runs on every recompute, so without this a click, a scroll or
        a refinement would be overwritten by the next redraw. Unticking the box
        rather than silently ignoring it keeps the reason visible on screen.
        """
        if self.controller.auto_detect_peaks:
            self.controller.auto_detect_peaks = False

    def clearFrequency(self):
        self.takeManualControl()
        self.controller.selected_freqs = []
        self.selectedQuefrencyLabel.setText("Selected quefrency: None")

        self.refresh()

    def refineFrequency(self):
        if not self.controller.selected_freqs:
            logging.warning("No selected quefrency to refine.")
            return

        self.takeManualControl()

        original = self.controller.selected_freqs[-1]
        refined = self.controller.refine_selected_quefrency()
        if refined is None:
            logging.warning(
                "Quefrency refinement found no usable peak around %.4f m; keeping it.",
                original)
            return

        self.controller.selected_freqs[-1] = refined
        self.refresh(restore_lim=True)

    def select_quefrency_at(self, ax, xdata):
        """Select the cepstrum bin nearest to a position on the quefrency axis."""
        if ax is None or xdata is None:
            return False

        # Check if the x-coordinate is within the axis limits
        xlim = ax.get_xlim()
        if not (xlim[0] <= xdata <= xlim[1]) or xdata < 0:
            return False
        if not self.controller.selected_freqs:
            self.controller.selected_freqs = []

        snapped_quefrency = self.controller.snap_quefrency_to_bin(xdata)
        if snapped_quefrency is None:
            return False

        self.takeManualControl()
        self.controller.selected_freqs.append(snapped_quefrency)
        self.refresh(restore_lim=True)
        return True

    def contextMenuActions(self, event):
        """Offer the same selection as the selector button on the canvas menu.

        Contributed to the canvas menu rather than popped from here, so that the
        annotation entries and this one share a single right-click menu.
        """
        return [(
            "Select quefrency",
            lambda menu_event: self.select_quefrency_at(
                menu_event.inaxes, menu_event.xdata),
            event.xdata is not None,
        )]

    def onclick(self, event):
        if self.is_navigation_mode_active():
            return

        if event.inaxes is None:
            return

        if event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:
            self.select_quefrency_at(event.inaxes, event.xdata)

    def on_scroll(self, event):
        if self.is_navigation_mode_active():
            return

        if event.inaxes is None or event.button not in ("up", "down"):
            return

        if not self.controller.move_selected_quefrency_by_bins(event.step):
            return

        self.takeManualControl()
        self.refresh(restore_lim=True)

    def is_navigation_mode_active(self):
        return bool(
            self.controller.canvas.toolbar and self.controller.canvas.toolbar.mode
        )

    def get_current_view_limits(self):
        if not self.controller.figure.axes:
            return None

        ax = self.controller.figure.axes[0]
        return ax.get_xlim(), ax.get_ylim()

    def restore_view_limits(self, view_limits):
        if view_limits is None or not self.controller.figure.axes:
            return

        ax = self.controller.figure.axes[0]
        x_limits, y_limits = view_limits
        ax.set_xlim(x_limits)
        ax.set_ylim(y_limits)
        self.controller.canvas.draw_idle()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        self.initQuefrencyRangeSlider(block_signals=True)
        self.initSpectrumLengthSlider(block_signals=True)
        self.initAutoDetectPeaksCheckbox(block_signals=True)
        self.initMachineSpeedSpinner(block_signals=True)

    def refresh(self, restore_lim=False):
        view_limits = self.get_current_view_limits() if restore_lim else None
        self.controller.updatePlot()
        self.restore_view_limits(view_limits)
        self.refresh_widgets()

        quefrency = self.selectedQuefrency()
        if quefrency is not None:
            amplitude = self.controller.get_cepstrum_amplitude_at(quefrency)
            self.selectedQuefrencyLabel.setText(
                f"Selected quefrency: {self.controller.describe_quefrency(quefrency, amplitude)}")
        else:
            self.selectedQuefrencyLabel.setText("Selected quefrency: None")

        if self.paperMachineDataWindow:
            self.paperMachineDataWindow.refresh_pm_data(
                self.controller.machine_speed, self.selectedFrequency())
