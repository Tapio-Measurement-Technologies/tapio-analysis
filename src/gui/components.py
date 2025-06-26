from PyQt6.QtWidgets import QApplication
from io import BytesIO
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtWidgets import QComboBox, QLabel, QDoubleSpinBox, QFileDialog, QCheckBox, QHBoxLayout, QMessageBox, QGridLayout, QPushButton
from PyQt6.QtGui import QAction, QIcon
from qtpy.QtCore import Qt, Signal
from superqt import QLabeledDoubleRangeSlider, QLabeledSlider, QLabeledDoubleSlider
from matplotlib.figure import Figure
from gui.annotable_canvas import AnnotableCanvas
import logging
import settings
import numpy as np
import pandas as pd
import io
import traceback

from gui.sample_selector import SampleSelectorWindow


class FineControlMixin:
    """
    A mixin to add fine control to SuperQt sliders.
    Fine control is activated by right-clicking or Ctrl+left-clicking the slider.
    This mixin must be used with a class that has a `_slider` attribute.
    """

    def _init_fine_control(self):
        self._fine_control_active = False
        self._fine_control_factor = settings.DOUBLE_SLIDER_FINE_CONTROL_FACTOR
        self.handle_radius = settings.DOUBLE_SLIDER_HANDLE_RADIUS

        self._drag_start_pos = None
        self._original_pos = None
        self._initializing_fine_control = False

        # Store original mouse handlers before overriding
        self._original_mousePressEvent = self._slider.mousePressEvent
        self._original_mouseMoveEvent = self._slider.mouseMoveEvent
        self._original_mouseReleaseEvent = self._slider.mouseReleaseEvent

        # Override the underlying slider's mouse events
        self._slider.mousePressEvent = self._slider_mouse_press_event
        self._slider.mouseReleaseEvent = self._slider_mouse_release_event
        self._slider.mouseMoveEvent = self._slider_mouse_move_event

    def _slider_mouse_press_event(self, event: QMouseEvent):
        """Handle mouse press events on the underlying slider to activate fine control."""
        if (event.button() == Qt.MouseButton.RightButton or
            (event.button() == Qt.MouseButton.LeftButton and
             event.modifiers() == Qt.KeyboardModifier.ControlModifier)):

            slider_rect = self._slider.rect()
            min_val, max_val = self._slider.minimum(), self._slider.maximum()
            current_value = self._slider.value()
            width = slider_rect.width()

            def value_to_pos(val):
                if max_val == min_val:
                    return 0
                return int((val - min_val) / (max_val - min_val) * width)

            click_x = int(event.position().x())

            handle_positions = []
            is_range_slider = isinstance(current_value, (list, tuple))

            if is_range_slider:
                low, high = current_value
                handle_positions.append(value_to_pos(low))
                handle_positions.append(value_to_pos(high))
            else:
                handle_positions.append(value_to_pos(current_value))

            on_handle = any(abs(click_x - pos) <=
                            self.handle_radius for pos in handle_positions)

            in_range = False
            if is_range_slider:
                low_pos, high_pos = handle_positions
                in_range = low_pos <= click_x <= high_pos

            if on_handle or in_range:
                self._fine_control_active = True
                self._initializing_fine_control = True
                self._drag_start_pos = event.position()
                self._original_pos = event.position()

                if event.button() == Qt.MouseButton.RightButton:
                    self._slider.blockSignals(True)
                    current_value_at_press = self._slider.value()
                    left_click_event = QMouseEvent(
                        event.Type.MouseButtonPress, event.position(), event.globalPosition(),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers()
                    )
                    self._original_mousePressEvent(left_click_event)
                    self._slider.setValue(current_value_at_press)
                    self._slider.blockSignals(False)
                    self._initializing_fine_control = False
                    return

                self._initializing_fine_control = False
            else:
                return  # Not on a handle or in range, do nothing

        self._original_mousePressEvent(event)

    def _slider_mouse_move_event(self, event: QMouseEvent):
        """Handle mouse move events for fine control."""
        if self._fine_control_active and self._drag_start_pos is not None and not self._initializing_fine_control:
            if event.buttons() & Qt.MouseButton.RightButton or \
               (event.buttons() & Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier):

                current_pos = event.position()
                delta = current_pos - self._drag_start_pos

                if abs(delta.x()) > 2 or abs(delta.y()) > 2:
                    scaled_delta = delta * self._fine_control_factor
                    scaled_pos = self._original_pos + scaled_delta

                    scaled_event = QMouseEvent(
                        event.Type.MouseMove, scaled_pos, event.globalPosition(),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, event.modifiers()
                    )
                    self._original_mouseMoveEvent(scaled_event)
                    return

        self._original_mouseMoveEvent(event)

    def _slider_mouse_release_event(self, event: QMouseEvent):
        """Handle mouse release events to deactivate fine control."""
        if self._fine_control_active:
            self._fine_control_active = False
            self._drag_start_pos = None
            self._original_pos = None

            if event.button() == Qt.MouseButton.RightButton:
                left_release_event = QMouseEvent(
                    event.Type.MouseButtonRelease, event.position(), event.globalPosition(),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, event.modifiers()
                )
                self._original_mouseReleaseEvent(left_release_event)
                return

        self._original_mouseReleaseEvent(event)

class ExtraQLabeledDoubleRangeSlider(FineControlMixin, QLabeledDoubleRangeSlider):
    sliderReleased = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slider.sliderReleased.connect(self.sliderReleased.emit)
        self._init_fine_control()

class ExtraQLabeledSlider(FineControlMixin, QLabeledSlider):
    sliderReleased = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slider.sliderReleased.connect(self.sliderReleased.emit)
        self._init_fine_control()

class ExtraQLabeledDoubleSlider(FineControlMixin, QLabeledDoubleSlider):
    sliderReleased = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slider.sliderReleased.connect(self.sliderReleased.emit)
        self._init_fine_control()

class MachineSpeedMixin:

    def initMachineSpeedSpinner(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.machineSpeedSpinBox.blockSignals(block_signals)
        self.machineSpeedSpinBox.setMinimum(0.0)
        self.machineSpeedSpinBox.setMaximum(3000)
        self.machineSpeedSpinBox.setSingleStep(0.1)
        self.machineSpeedSpinBox.setValue(self.controller.machine_speed)
        self.machineSpeedSpinBox.blockSignals(False)

    def addMachineSpeedSpinner(self, layout):
        self.machineSpeedLabel = QLabel("Machine Speed [m/min]:")
        layout.addWidget(self.machineSpeedLabel)
        self.machineSpeedSpinBox = QDoubleSpinBox()
        self.initMachineSpeedSpinner()

        layout.addWidget(self.machineSpeedSpinBox)
        self.machineSpeedSpinBox.valueChanged.connect(self.machineSpeedChanged)

    def machineSpeedChanged(self, value):
        self.controller.machine_speed = value
        self.refresh()


class FrequencyRangeMixin:

    def initFrequencyRangeSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.frequencyRangeSlider.blockSignals(block_signals)
        self.frequencyRangeSlider.setDecimals(1)
        self.frequencyRangeSlider.setRange(0, self.controller.max_freq)
        self.frequencyRangeSlider.setValue(
            (self.controller.frequency_range_low, self.controller.frequency_range_high))
        self.frequencyRangeSlider.blockSignals(False)

    def addFrequencyRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.frequencyRangeLabel = QLabel("Frequency range [1/m]")
        layout.addWidget(self.frequencyRangeLabel)
        self.frequencyRangeSlider = ExtraQLabeledDoubleRangeSlider(
            Qt.Orientation.Horizontal)
        self.initFrequencyRangeSlider()

        if live_update:
            self.frequencyRangeSlider.valueChanged.connect(
                self.frequencyRangeChanged)
        else:
            self.frequencyRangeSlider.sliderReleased.connect(
                self.frequencyRangeChanged)
            self.frequencyRangeSlider.editingFinished.connect(
                self.frequencyRangeChanged)
        layout.addWidget(self.frequencyRangeSlider)

    def frequencyRangeChanged(self):
        self.controller.frequency_range_low, self.controller.frequency_range_high = self.frequencyRangeSlider.value()
        self.refresh()  # Optionally refresh the plot if needed


class AnalysisRangeMixin:

    def initAnalysisRangeSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.analysisRangeSlider.blockSignals(block_signals)
        self.analysisRangeSlider.setDecimals(settings.ANALYSIS_RANGE_DECIMALS)
        # Ensure measurement is accessible
        # self.max_dist = np.max(self.measurement.distances)
        self.analysisRangeSlider.setRange(0, self.controller.max_dist)
        self.analysisRangeSlider.setValue(
            (self.controller.analysis_range_low, self.controller.analysis_range_high))
        self.analysisRangeSlider.blockSignals(False)

    def addAnalysisRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.analysisRangeLabel = QLabel("Analysis range [m]")
        layout.addWidget(self.analysisRangeLabel)
        self.analysisRangeSlider = ExtraQLabeledDoubleRangeSlider(
            Qt.Orientation.Horizontal)
        self.initAnalysisRangeSlider()

        if live_update:
            self.analysisRangeSlider.valueChanged.connect(
                self.analysisRangeChanged)
        else:
            self.analysisRangeSlider.sliderReleased.connect(
                self.analysisRangeChanged)
            self.analysisRangeSlider.editingFinished.connect(
                self.analysisRangeChanged)
        layout.addWidget(self.analysisRangeSlider)

    def analysisRangeChanged(self):
        self.controller.analysis_range_low, self.controller.analysis_range_high = self.analysisRangeSlider.value()
        self.refresh()


class ChannelMixin:

    def initChannelSelector(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.channelComboBox.blockSignals(block_signals)
        initial_channel = self.controller.channel
        if initial_channel is not None and initial_channel in self.measurement.channels:
            initial_index = self.channelComboBox.findText(initial_channel)
            if initial_index >= 0:  # Ensure the text was found
                self.channelComboBox.setCurrentIndex(initial_index)
        self.channelComboBox.blockSignals(False)

    def addChannelSelector(self, layout):
        self.channelComboBox = QComboBox()
        self.channelComboBox.addItems(self.measurement.channels)
        self.initChannelSelector()
        layout.addWidget(self.channelComboBox)
        self.channelComboBox.currentIndexChanged.connect(self.channelChanged)

    def channelChanged(self):
        self.controller.channel = self.channelComboBox.currentText()
        self.refresh()


class DoubleChannelMixin:

    def initChannelSelectors(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.channelSelector1.blockSignals(block_signals)
        self.channelSelector2.blockSignals(block_signals)

        channel1 = self.controller.channel1
        channel2 = self.controller.channel2
        if channel1 is not None and channel1 in self.controller.channels:
            index = self.channelSelector1.findText(channel1)
            if index >= 0:  # Ensure the text was found
                self.channelSelector1.setCurrentIndex(index)

        if channel2 is not None and channel2 in self.controller.channels:
            index = self.channelSelector2.findText(channel2)
            if index >= 0:  # Ensure the text was found
                self.channelSelector2.setCurrentIndex(index)

        self.channelSelector1.blockSignals(False)
        self.channelSelector2.blockSignals(False)

    def addChannelSelectors(self, layout):
        # Channel selectors
        channelSelectorLayout = QHBoxLayout()
        self.channelSelector1 = QComboBox()
        self.channelSelector2 = QComboBox()
        for channel in self.controller.channels:
            self.channelSelector1.addItem(channel)
            self.channelSelector2.addItem(channel)
        self.initChannelSelectors()
        self.channelSelector1.currentIndexChanged.connect(self.channelsChanged)
        self.channelSelector2.currentIndexChanged.connect(self.channelsChanged)
        channelSelectorLayout.addWidget(self.channelSelector1)
        channelSelectorLayout.addWidget(self.channelSelector2)
        layout.addLayout(channelSelectorLayout)

    def channelsChanged(self):
        self.controller.channel1 = self.channelSelector1.currentText()
        self.controller.channel2 = self.channelSelector2.currentText()
        self.refresh()


class SpectrumLengthMixin:

    def initSpectrumLengthSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.spectrumLengthSlider.blockSignals(block_signals)
        self.spectrumLengthSlider.setMinimum(
            self.controller.spectrum_length_slider_min)
        self.spectrumLengthSlider.setMaximum(
            self.controller.spectrum_length_slider_max)
        self.spectrumLengthSlider.setSingleStep(1000)
        self.spectrumLengthSlider.setValue(self.controller.nperseg)
        self.spectrumLengthSlider.blockSignals(False)

    def addSpectrumLengthSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.spectrumLengthLabel = QLabel("Window length [m]")
        layout.addWidget(self.spectrumLengthLabel)
        self.spectrumLengthSlider = ExtraQLabeledSlider(
            Qt.Orientation.Horizontal)
        self.initSpectrumLengthSlider()
        layout.addWidget(self.spectrumLengthSlider)

        if live_update:
            self.spectrumLengthSlider.valueChanged.connect(
                self.spectrumLengthChanged)
        else:
            self.spectrumLengthSlider.sliderReleased.connect(
                self.spectrumLengthChanged)
            self.spectrumLengthSlider.editingFinished.connect(
                self.spectrumLengthChanged)

    def spectrumLengthChanged(self):
        # Update your nperseg value based on the slider
        self.controller.nperseg = self.spectrumLengthSlider.value()
        self.refresh()  # Refresh the plot with the new spectrum length


class WaterfallOffsetMixin:

    def initWaterfallOffsetSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.waterfallOffsetSlider.blockSignals(block_signals)
        self.waterfallOffsetSlider.setMinimum(
            settings.WATERFALL_OFFSET_LOW_DEFAULT)
        self.waterfallOffsetSlider.setMaximum(
            settings.WATERFALL_OFFSET_HIGH_DEFAULT)
        self.waterfallOffsetSlider.setValue(self.controller.waterfall_offset)
        self.waterfallOffsetSlider.blockSignals(False)

    def addWaterfallOffsetSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.waterfallOffsetLabel = QLabel("Waterfall y-offset")
        layout.addWidget(self.waterfallOffsetLabel)
        self.waterfallOffsetSlider = ExtraQLabeledDoubleSlider(
            Qt.Orientation.Horizontal)
        self.initWaterfallOffsetSlider()
        layout.addWidget(self.waterfallOffsetSlider)

        if live_update:
            self.waterfallOffsetSlider.valueChanged.connect(
                self.waterfallOffsetChanged)
        else:
            self.waterfallOffsetSlider.sliderReleased.connect(
                self.waterfallOffsetChanged)
            self.waterfallOffsetSlider.editingFinished.connect(
                self.waterfallOffsetChanged)

    def waterfallOffsetChanged(self):
        self.controller.waterfall_offset = self.waterfallOffsetSlider.value()
        self.refresh()


class BandPassFilterMixin:

    def bandPassFilterRangeChanged(self):
        self.controller.band_pass_low, self.controller.band_pass_high = self.bandPassFilterSlider.value()
        self.refresh()
        self._update_wavelength_label()

    def _update_wavelength_label(self):
        # Convert frequencies (1/m) to wavelengths (cm)
        low, high = self.bandPassFilterSlider.value()
        if high > 0:
            wavelength_high = 100 / \
                low if low > 0 else float('inf')  # Convert to cm
            wavelength_low = 100/high  # Convert to cm
            if wavelength_high == float('inf'):
                wavelength_text = f"∞ - {wavelength_low:.{settings.BAND_PASS_FILTER_WAVELENGTH_DECIMALS}f}"
            else:
                wavelength_text = f"{wavelength_high:.{settings.BAND_PASS_FILTER_WAVELENGTH_DECIMALS}f} - {wavelength_low:.{settings.BAND_PASS_FILTER_WAVELENGTH_DECIMALS}f}"
            self.bandPassFilterLabel.setText(
                f"Band pass filter [1/m]\t λ = {wavelength_text} cm")
        else:
            self.bandPassFilterLabel.setText("Band pass filter [1/m]")

    def initBandPassRangeSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.bandPassFilterSlider.blockSignals(block_signals)
        self.bandPassFilterSlider.setRange(0, (self.controller.fs / 2) *
                                           ((settings.FILTER_NUMTAPS - 1) / settings.FILTER_NUMTAPS))
        self.bandPassFilterSlider.setValue(
            (self.controller.band_pass_low, self.controller.band_pass_high))
        self.bandPassFilterSlider.blockSignals(False)
        self._update_wavelength_label()

    def addBandPassRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        # Band pass filter range slider
        self.bandPassFilterLabel = QLabel("Band pass filter [1/m]")
        layout.addWidget(self.bandPassFilterLabel)
        self.bandPassFilterSlider = ExtraQLabeledDoubleRangeSlider(
            Qt.Orientation.Horizontal)
        self.bandPassFilterSlider.setDecimals(
            settings.BAND_PASS_FILTER_DECIMALS)
        self.bandPassFilterSlider.setSingleStep(
            settings.BAND_PASS_FILTER_SINGLESTEP)
        self.initBandPassRangeSlider()

        if live_update:
            self.bandPassFilterSlider.valueChanged.connect(
                self.bandPassFilterRangeChanged)
        else:
            self.bandPassFilterSlider.sliderReleased.connect(
                self.bandPassFilterRangeChanged)
            self.bandPassFilterSlider.editingFinished.connect(
                self.bandPassFilterRangeChanged)

        layout.addWidget(self.bandPassFilterSlider)

        self.bandPassFilterSlider.setTracking(True)


class SampleSelectMixin:

    def toggleSelectSamples(self):
        """Toggle the visibility of the sample selector window."""
        if self.sampleSelectorWindow is None:
            self.sampleSelectorWindow = SampleSelectorWindow(
                self.controller.selected_samples, self.selectSamples, self.measurement)
            self.sampleSelectorWindow.show()
        elif self.sampleSelectorWindow.isVisible():
            self.sampleSelectorWindow.hide()
        else:
            self.sampleSelectorWindow.show()

    def selectSamples(self, samples):
        """Callback function to handle sample selection from the SampleSelectorWindow."""
        self.controller.selected_samples = samples
        self.controller.selected_samples.sort()
        print("Got updated samples from selector window")
        print(self.controller.selected_samples)
        self.refresh()


class ShowUnfilteredMixin:

    def initShowUnfilteredCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showUnfilteredCheckBox.blockSignals(block_signals)
        show_unfiltered_data = self.controller.show_unfiltered_data
        self.showUnfilteredCheckBox.setChecked(show_unfiltered_data)
        self.showUnfilteredCheckBox.blockSignals(False)

    def addShowUnfilteredCheckbox(self, layout):
        self.showUnfilteredCheckBox = QCheckBox("Show unfiltered data", self)
        self.initShowUnfilteredCheckbox()
        self.showUnfilteredCheckBox.stateChanged.connect(
            self.update_show_unfiltered)
        layout.addWidget(self.showUnfilteredCheckBox)

    def update_show_unfiltered(self):
        state = self.showUnfilteredCheckBox.isChecked()
        self.controller.show_unfiltered_data = state
        self.refresh()


class ShowWavelengthMixin:

    def initShowWavelengthCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.wavelengthCheckbox.blockSignals(block_signals)
        show_wavelength = self.controller.show_wavelength
        self.wavelengthCheckbox.setChecked(show_wavelength)
        self.wavelengthCheckbox.blockSignals(False)

    def addShowWavelengthCheckbox(self, layout):
        self.wavelengthCheckbox = QCheckBox("Wavelength labels", self)
        self.initShowWavelengthCheckbox()
        self.wavelengthCheckbox.stateChanged.connect(
            self.update_show_wavelength)
        layout.addWidget(self.wavelengthCheckbox)

    def update_show_wavelength(self):
        state = self.wavelengthCheckbox.isChecked()
        self.controller.show_wavelength = state
        self.refresh()


class AutoDetectPeaksMixin:

    def initAutoDetectPeaksCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.autodetectCheckbox.blockSignals(block_signals)
        show_autodetect = self.controller.auto_detect_peaks
        self.autodetectCheckbox.setChecked(show_autodetect)
        self.autodetectCheckbox.blockSignals(False)

    def addAutoDetectPeaksCheckbox(self, layout):
        self.autodetectCheckbox = QCheckBox("Detect peaks", self)
        self.initAutoDetectPeaksCheckbox()
        self.autodetectCheckbox.stateChanged.connect(
            self.update_autodetect)
        layout.addWidget(self.autodetectCheckbox)

    def update_autodetect(self):
        state = self.autodetectCheckbox.isChecked()
        self.controller.auto_detect_peaks = state
        self.refresh()


class ShowProfilesMixin:

    def initShowProfilesCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showProfilesCheckBox.blockSignals(block_signals)
        show_profiles = self.controller.show_profiles
        self.showProfilesCheckBox.setChecked(show_profiles)
        self.showProfilesCheckBox.blockSignals(False)

    def addShowProfilesCheckbox(self, layout):
        self.showProfilesCheckBox = QCheckBox("Show individual profiles", self)
        self.initShowProfilesCheckbox()
        self.showProfilesCheckBox.stateChanged.connect(
            self.update_show_profiles)
        layout.addWidget(self.showProfilesCheckBox)

    def update_show_profiles(self):
        state = self.showProfilesCheckBox.isChecked()
        self.controller.show_profiles = state
        self.refresh()


class ShowMinMaxMixin:

    def initShowMinMaxCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showMinMaxCheckBox.blockSignals(block_signals)
        show_min_max = self.controller.show_min_max
        self.showMinMaxCheckBox.setChecked(show_min_max)
        self.showMinMaxCheckBox.blockSignals(False)

    def addShowMinMaxCheckbox(self, layout):
        self.showMinMaxCheckBox = QCheckBox("Show min/max", self)
        self.initShowMinMaxCheckbox()
        self.showMinMaxCheckBox.stateChanged.connect(self.update_show_min_max)
        layout.addWidget(self.showMinMaxCheckBox)

    def update_show_min_max(self):
        state = self.showMinMaxCheckBox.isChecked()
        self.controller.show_min_max = state
        self.refresh()


class ShowLegendMixin:

    def initShowLegendCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showLegendCheckBox.blockSignals(block_signals)
        show_legend = self.controller.show_legend
        self.showLegendCheckBox.setChecked(show_legend)
        self.showLegendCheckBox.blockSignals(False)

    def addShowLegendCheckbox(self, layout):
        self.showLegendCheckBox = QCheckBox("Show legend", self)
        self.initShowLegendCheckbox()
        self.showLegendCheckBox.stateChanged.connect(self.update_show_legend)
        layout.addWidget(self.showLegendCheckBox)

    def update_show_legend(self):
        state = self.showLegendCheckBox.isChecked()
        self.controller.show_legend = state
        self.refresh()


class ShowConfidenceIntervalMixin:

    def initShowConfidenceIntervalCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showConfidenceIntervalCheckbox.blockSignals(block_signals)
        show_conf_int = self.controller.confidence_interval is not None
        self.showConfidenceIntervalCheckbox.setChecked(show_conf_int)
        self.showConfidenceIntervalCheckbox.blockSignals(False)

    def addShowConfidenceIntervalCheckbox(self, layout, interval):
        self.showConfidenceIntervalCheckbox = QCheckBox(
            f"Show {interval * 100}% confidence interval", self)
        self.confidence_interval = interval
        self.initShowConfidenceIntervalCheckbox()
        self.showConfidenceIntervalCheckbox.stateChanged.connect(
            self.update_show_confidence_interval)
        layout.addWidget(self.showConfidenceIntervalCheckbox)

    def update_show_confidence_interval(self):
        state = self.showConfidenceIntervalCheckbox.isChecked()
        self.controller.confidence_interval = self.confidence_interval if state else None
        self.refresh()


class ShowTimeLabelsMixin:

    def initShowTimeLabelsCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showTimeLabelsCheckbox.blockSignals(block_signals)
        show_time_labels = self.controller.show_time_labels
        self.showTimeLabelsCheckbox.setChecked(show_time_labels)
        self.showTimeLabelsCheckbox.blockSignals(False)

    def addShowTimeLabelsCheckbox(self, layout):
        self.showTimeLabelsCheckbox = QCheckBox("Show time labels", self)
        self.initShowTimeLabelsCheckbox()
        self.showTimeLabelsCheckbox.stateChanged.connect(
            self.update_show_time_labels)
        layout.addWidget(self.showTimeLabelsCheckbox)

    def update_show_time_labels(self):
        state = self.showTimeLabelsCheckbox.isChecked()
        self.controller.show_time_labels = state
        self.refresh()


class ExportMixin:

    def __init__(self):
        super().__init__()

    def initExportAction(self, window, text="Export"):
        self.window = window
        exportAction = QAction(text, self.window)
        exportAction.triggered.connect(self.export)
        exportAction.setShortcut("Ctrl+E")
        exportAction.setStatusTip(text)
        return exportAction

    def export(self):
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileName, selectedFilter = QFileDialog.getSaveFileName(self.window,
                                                               "Save data as...",
                                                               "",
                                                               "Excel Files (*.xlsx);;CSV Files (*.csv)",
                                                               options=options)
        if fileName:
            data = self.getExportData()  # getExportData is implemented in the subclass
            if 'Excel' in selectedFilter:
                if not fileName.endswith('.xlsx'):
                    fileName += '.xlsx'
                data.to_excel(fileName, index=False)
                logging.info("Exported data to Excel file successfully.")
            elif 'CSV' in selectedFilter:
                if not fileName.endswith('.csv'):
                    fileName += '.csv'
                data.to_csv(fileName, index=False)
                logging.info("Exported data to CSV file successfully.")

    def getExportData(self):
        raise NotImplementedError(
            "Subclasses should implement this method to return the data as a DataFrame.")


class ExtraDataMixin:

    def addExtraDataWidget(self, layout):
        self.extraDataLabel = QLabel("Extra data")
        # Extra data controls
        self.extraDataComboBox = QComboBox(self)
        self.extraDataCheckBox = QCheckBox("Show extra data", self)
        self.sameScaleCheckBox = QCheckBox(
            "Use same scale for primary and secondary axis", self)
        self.extraDataComboBox.currentIndexChanged.connect(
            self.update_extra_data)
        self.extraDataCheckBox.stateChanged.connect(
            self.update_show_extra_data)
        self.sameScaleCheckBox.stateChanged.connect(self.update_use_same_scale)

        layout.addWidget(self.extraDataLabel)
        layout.addWidget(self.extraDataComboBox)
        layout.addWidget(self.extraDataCheckBox)
        layout.addWidget(self.sameScaleCheckBox)

        # Extra data adjustment sliders
        self.extraDataAdjustStartSlider = ExtraQLabeledDoubleSlider(self)
        self.extraDataAdjustStartSlider.setOrientation(Qt.Orientation.Horizontal)
        self.extraDataAdjustStartSlider.sliderReleased.connect(
            self.update_adjust_extra_data_start)
        self.extraDataAdjustStartSlider.editingFinished.connect(
            self.update_adjust_extra_data_start)

        self.extraDataAdjustEndSlider = ExtraQLabeledDoubleSlider(self)
        self.extraDataAdjustEndSlider.setOrientation(Qt.Orientation.Horizontal)
        self.extraDataAdjustEndSlider.sliderReleased.connect(
            self.update_adjust_extra_data_end)
        self.extraDataAdjustEndSlider.editingFinished.connect(
            self.update_adjust_extra_data_end)

        # Slider layout
        slider_layout = QVBoxLayout()
        self.extraDataAdjustStartLabel = QLabel("Adjust extra data start [m]")
        slider_layout.addWidget(self.extraDataAdjustStartLabel)
        slider_layout.addWidget(self.extraDataAdjustStartSlider)
        self.extraDataAdjustEndLabel = QLabel("Adjust extra data end [m]")
        slider_layout.addWidget(self.extraDataAdjustEndLabel)
        slider_layout.addWidget(self.extraDataAdjustEndSlider)

        # Add sliders layout to the main layout
        layout.addLayout(slider_layout)

        self.loadExtraDataButton = QPushButton("Load extra data")
        self.loadExtraDataButton.clicked.connect(self.loadExtraData)
        layout.addWidget(self.loadExtraDataButton)

        self.extraDataLabel.hide()
        self.extraDataComboBox.hide()
        self.extraDataCheckBox.hide()
        self.sameScaleCheckBox.hide()
        self.extraDataAdjustStartSlider.hide()
        self.extraDataAdjustEndSlider.hide()

        self.extraDataAdjustStartLabel.hide()
        self.extraDataAdjustEndLabel.hide()

    def loadExtraData(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Load extra data", "", "Excel Files (*.xlsx)")
            if file_path:
                self.controller.extra_data = pd.read_excel(
                    file_path, sheet_name=None)
                self.extraDataComboBox.clear()
                for sheet_name, df in self.controller.extra_data.items():
                    self.extraDataComboBox.addItem(sheet_name)
                    unit = df.columns[1].split(
                        '[')[-1].replace(']', '').strip()
                    self.controller.extra_data_units[sheet_name] = unit
                self.extraDataLabel.show()
                self.extraDataAdjustStartLabel.show()
                self.extraDataAdjustEndLabel.show()
                self.extraDataComboBox.show()
                self.extraDataCheckBox.show()
                self.sameScaleCheckBox.show()

                self.extraDataAdjustStartSlider.setMinimum(
                    -1 * settings.EXTRA_DATA_ADJUST_RANGE)
                self.extraDataAdjustStartSlider.setMaximum(
                    settings.EXTRA_DATA_ADJUST_RANGE)
                self.extraDataAdjustStartSlider.setValue(0)
                self.extraDataAdjustStartSlider.show()

                self.extraDataAdjustEndSlider.setMinimum(
                    -1 * settings.EXTRA_DATA_ADJUST_RANGE)
                self.extraDataAdjustEndSlider.setMaximum(
                    settings.EXTRA_DATA_ADJUST_RANGE)
                self.extraDataAdjustEndSlider.setValue(0)
                self.extraDataAdjustEndSlider.show()

                # Show extra data by default
                self.extraDataCheckBox.setChecked(True)

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to load file: {str(e)}")

    def update_adjust_extra_data_start(self):
        state = self.extraDataAdjustStartSlider.value()
        self.controller.extra_data_adjust_start = state
        self.refresh()

    def update_adjust_extra_data_end(self):
        state = self.extraDataAdjustEndSlider.value()
        self.controller.extra_data_adjust_end = state
        self.refresh()

    def update_adjust_extra_data_start(self):
        state = self.extraDataAdjustStartSlider.value()
        self.controller.extra_data_adjust_start = state
        self.refresh()

    def update_show_extra_data(self):
        state = self.extraDataCheckBox.isChecked()
        self.controller.show_extra_data = state
        self.refresh()

    def update_extra_data(self):
        selected_sheet = self.extraDataComboBox.currentText()
        self.controller.selected_sheet = selected_sheet
        self.refresh()

    def update_use_same_scale(self):
        state = self.sameScaleCheckBox.isChecked()
        self.controller.use_same_scale = state
        self.refresh()


class StatsMixin:

    def updateStatistics(self, data, show_units=True):
        units = self.measurement.units[self.controller.channel] if show_units else ""

        if not len(data):
            self.meanLabel.setText(f"Mean: -- {units}")
            self.stdLabel.setText(f"σ: -- {units}")
            self.minLabel.setText(f"Min: -- {units}")
            self.maxLabel.setText(f"Max: -- {units}")
            self.rangeLabel.setText(f"Range: -- {units}")
            return

        mean = np.mean(data)
        std = np.std(data)
        min_val = np.min(data)
        max_val = np.max(data)
        range_val = max_val - min_val

        self.meanLabel.setText(
            f"Mean: {mean:.{settings.STATISTICS_DECIMALS}f} {units}")
        self.stdLabel.setText(
            f"σ: {std:.{settings.STATISTICS_DECIMALS}f} {units}")
        self.minLabel.setText(
            f"Min: {min_val:.{settings.STATISTICS_DECIMALS}f} {units}")
        self.maxLabel.setText(
            f"Max: {max_val:.{settings.STATISTICS_DECIMALS}f} {units}")
        self.rangeLabel.setText(
            f"Range: {range_val:.{settings.STATISTICS_DECIMALS}f} {units}")

class ShowAnnotationsMixin:
    def initShowAnnotationsCheckbox(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.showAnnotationsCheckBox.blockSignals(block_signals)
        show_annotations = self.controller.show_annotations
        self.showAnnotationsCheckBox.setChecked(show_annotations)
        self.showAnnotationsCheckBox.blockSignals(False)

    def addShowAnnotationsCheckbox(self, layout):
        self.showAnnotationsCheckBox = QCheckBox("Show annotations")
        self.initShowAnnotationsCheckbox()
        self.showAnnotationsCheckBox.stateChanged.connect(
            self.update_show_annotations)
        layout.addWidget(self.showAnnotationsCheckBox)

    def update_show_annotations(self):
        state = self.showAnnotationsCheckBox.isChecked()
        self.controller.show_annotations = state
        self.refresh()


class PlotMixin:

    def __init__(self):
        super().__init__()

        self.figure = Figure()
        self.canvas = AnnotableCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas)

    def addPlot(self, layout):
        plotLayout = QVBoxLayout()
        plotLayout.addWidget(self.canvas, stretch=1)
        plotLayout.addWidget(self.toolbar)
        layout.addLayout(plotLayout, stretch=1)

    def getCanvas(self):
        if not hasattr(self, 'canvas'):
            self.__init__()
        return self.canvas

    def updatePlot(self):
        try:
            annotations = self.canvas.get_annotations()
            self.plot()
            # Re-apply interactive annotations
            self.canvas.set_annotations(annotations)

        except Exception as e:
            # Print the exception details with traceback
            print("Exception occurred:")
            traceback.print_exc()
            self.figure.text(0.5, 0.5, "Invalid parameters",
                             fontsize=14, ha='center', va='center')
            self.canvas.draw()

    def getPlotImage(self, format="png", dpi=300):
        buf = io.BytesIO()
        self.figure.savefig(buf, format=format, dpi=dpi)
        return buf

    def plot(self):
        raise NotImplementedError("Subclasses should implement this method.")


class CopyPlotMixin:
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            # Attempt to copy the plot if it exists
            if hasattr(self, 'plot') and self.plot:
                self.copyPlotToClipboard(self.plot)
            else:
                print("Warning: No plot available to copy.")
                return

        parent = super(CopyPlotMixin, self)
        if hasattr(parent, 'keyPressEvent'):
            parent.keyPressEvent(event)

    def copyPlotToClipboard(self, plot):
        """
        Copies the given plot's figure to the clipboard.

        Parameters:
        - plot: The matplotlib plot canvas to copy.
        """
        try:
            buffer = BytesIO()
            plot.figure.savefig(buffer, format='png', dpi=300)
            buffer.seek(0)

            # Convert buffer to QImage
            image = QImage()
            image.loadFromData(buffer.read(), format='PNG')
            buffer.close()

            # Copy to clipboard
            clipboard = QApplication.clipboard()
            clipboard.setImage(image)
            print("Plot copied to clipboard.")
        except Exception as e:
            print(f"Error copying plot to clipboard: {e}")


class ChildWindowCloseMixin:
    def closeEvent(self, event):
        # Close the paper machine data window if it exists
        if hasattr(self, 'paperMachineDataWindow') and self.paperMachineDataWindow:
            self.paperMachineDataWindow.close()
            self.paperMachineDataWindow = None

        # Close the SOS analysis window if it exists
        if hasattr(self, 'sosAnalysisWindow') and self.sosAnalysisWindow:
            self.sosAnalysisWindow.close()
            self.sosAnalysisWindow = None

        # Close the sample selector window if it exists
        if hasattr(self, 'sampleSelectorWindow') and self.sampleSelectorWindow:
            self.sampleSelectorWindow.close()
            self.sampleSelectorWindow = None


class StatWidget(QWidget):
    def __init__(self, name, units=""):
        super().__init__()
        self.name = name
        self.units = units
        self.value = None

        self.setObjectName("statWidget")
        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(5, 5, 5, 5)

        self.label = QLabel(
            f"{self.name} [{self.units}]" if units else self.name)
        self.label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.label.setStyleSheet(
            "font-size: 12px; background-color: transparent;")
        self.layout.addWidget(self.label)

        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.value_label.setStyleSheet(
            "font-size: 20px; background-color: transparent;")
        self.layout.addWidget(self.value_label)

        self.setLayout(self.layout)

    def update_value(self, value):
        if value is not None:
            self.value = value
            self.value_label.setText(f"{self.value:.2f}")
        else:
            self.value_label.setText("--")


class StatsWidget(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(2)

        # Header with title and copy button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(2)

        title_label = QLabel("Statistics")
        title_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(title_label)

        # Add stretch to push the button to the right
        header_layout.addStretch()

        # Create copy button with icon
        self.copy_button = QPushButton()
        self.copy_button.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_button.setToolTip("Copy statistics to clipboard")
        self.copy_button.setFixedSize(24, 24)
        self.copy_button.clicked.connect(self.copy_stats_to_clipboard)
        header_layout.addWidget(self.copy_button)

        main_layout.addLayout(header_layout)

        # Stats grid
        grid_layout = QGridLayout()
        grid_layout.setSpacing(2)

        self.widgets = {
            'mean': StatWidget("Mean"),
            'std': StatWidget("σ"),
            'cv': StatWidget("CV", "%"),  # CV always in percent
            'min': StatWidget("Min"),
            'max': StatWidget("Max"),
            'range': StatWidget("Range"),
        }

        for index, widget in enumerate(self.widgets.values()):
            grid_layout.addWidget(widget, 0, index)
            grid_layout.setColumnMinimumWidth(index, 80)

        main_layout.addLayout(grid_layout)
        self.setLayout(main_layout)

    def update_units(self, unit):
        """Update the units for all widgets except CV (which is always in %)"""
        for name, widget in self.widgets.items():
            if name != 'cv':  # Skip CV as it's always in percent
                widget.units = unit
                widget.label.setText(
                    f"{widget.name} [{widget.units}]" if widget.units else widget.name)

    def update_statistics(self, profile_data, unit=None):
        """Update statistics with optional unit update"""
        if unit is not None:
            self.update_units(unit)

        if profile_data is not None:
            self.widgets['mean'].update_value(profile_data.mean())
            self.widgets['std'].update_value(profile_data.std())
            self.widgets['cv'].update_value(profile_data.std(
            ) / profile_data.mean() * 100 if profile_data.mean() != 0 else None)
            self.widgets['min'].update_value(profile_data.min())
            self.widgets['max'].update_value(profile_data.max())
            self.widgets['range'].update_value(
                profile_data.max() - profile_data.min())
        else:
            for widget in self.widgets.values():
                widget.update_value(None)

    def copy_stats_to_clipboard(self):
        clipboard = QApplication.clipboard()

        try:
            # Create formatted text for Word
            text_format = []
            for name, widget in self.widgets.items():
                value = widget.value_label.text()
                unit = widget.units
                text_format.append(f"{widget.name}: {value} {unit}")

            # Create TSV format for Excel
            tsv_format = ["Statistic\tValue\tUnit"]
            for name, widget in self.widgets.items():
                value = widget.value_label.text()
                unit = widget.units
                tsv_format.append(f"{widget.name}\t{value}\t{unit}")

            # Set text format only (more reliable)
            clipboard.setText("\n".join(text_format))

            # Optional: Try to set TSV format if needed
            try:
                mime_data = clipboard.mimeData()
                mime_data.setData("text/tab-separated-values",
                                  "\n".join(tsv_format).encode())
                clipboard.setMimeData(mime_data)
            except:
                # If TSV format fails, we still have the text format
                pass

        except Exception as e:
            print(f"Error copying to clipboard: {str(e)}")
