from PyQt6.QtWidgets import QApplication
from io import BytesIO
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT as NavigationToolbar
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtWidgets import QComboBox, QLabel, QDoubleSpinBox, QFileDialog, QCheckBox, QHBoxLayout, QMessageBox
from PyQt6.QtGui import QAction
from qtpy.QtCore import Qt, Signal
from superqt import QLabeledDoubleRangeSlider, QLabeledSlider, QLabeledDoubleSlider
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import logging
import settings
import numpy as np
import pandas as pd
import io
import traceback

from gui.sample_selector import SampleSelectorWindow


class ExtraQLabeledDoubleRangeSlider(QLabeledDoubleRangeSlider):
    sliderReleased = Signal(tuple)  # Define the new signal for slider release

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._slider.sliderReleased.connect(self._on_slider_released)

    def _on_slider_released(self):
        value = self._slider.value()
        self.sliderReleased.emit((value[0], value[1]))


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
        # Ensure dataMixin is accessible
        # self.max_dist = np.max(self.dataMixin.distances)
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
        if initial_channel is not None and initial_channel in self.dataMixin.channels:
            initial_index = self.channelComboBox.findText(initial_channel)
            if initial_index >= 0:  # Ensure the text was found
                self.channelComboBox.setCurrentIndex(initial_index)
        self.channelComboBox.blockSignals(False)

    def addChannelSelector(self, layout):
        self.channelComboBox = QComboBox()
        self.channelComboBox.addItems(self.dataMixin.channels)
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


class ExtraQLabeledSlider(QLabeledSlider):
    pass

    # sliderReleased = Signal(int)

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.sliderReleased.connect(self._on_slider_released)

    # def _on_slider_released(self):
    #     value = self._slider.value()
    #     self.sliderReleased.emit(value)


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
        self.bandPassFilterLabel = QLabel("Waterfall y-offset")
        layout.addWidget(self.bandPassFilterLabel)
        self.waterfallOffsetSlider = QLabeledDoubleSlider(
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

    def initBandPassRangeSlider(self, block_signals=False):
        # Prevent recursive refresh calls when updating values elsewhere
        self.bandPassFilterSlider.blockSignals(block_signals)
        self.bandPassFilterSlider.setRange(0, (self.controller.fs / 2) *
                                           ((settings.FILTER_NUMTAPS - 1) / settings.FILTER_NUMTAPS))
        self.bandPassFilterSlider.setValue(
            (self.controller.band_pass_low, self.controller.band_pass_high))

        self.bandPassFilterSlider.blockSignals(False)

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
        # self.bandPassFilterSlider.setSizeIncrement(0.001)
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
                self.controller.selected_samples, self.selectSamples)
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
        self.extraDataAdjustStartSlider = QLabeledDoubleSlider(self)
        self.extraDataAdjustStartSlider.setOrientation(Qt.Horizontal)
        self.extraDataAdjustStartSlider.sliderReleased.connect(
            self.update_adjust_extra_data_start)
        self.extraDataAdjustStartSlider.editingFinished.connect(
            self.update_adjust_extra_data_start)

        self.extraDataAdjustEndSlider = QLabeledDoubleSlider(self)
        self.extraDataAdjustEndSlider.setOrientation(Qt.Horizontal)
        self.extraDataAdjustEndSlider.sliderReleased.connect(
            self.update_adjust_extra_data_end)
        self.extraDataAdjustEndSlider.editingFinished.connect(
            self.update_adjust_extra_data_end)

        # Slider layout
        slider_layout = QHBoxLayout()
        self.extraDataAdjustStartLabel = QLabel("Adjust extra data start [m]")
        slider_layout.addWidget(self.extraDataAdjustStartLabel)
        slider_layout.addWidget(self.extraDataAdjustStartSlider)
        self.extraDataAdjustEndLabel = QLabel("Adjust extra data end [m]")
        slider_layout.addWidget(self.extraDataAdjustEndLabel)
        slider_layout.addWidget(self.extraDataAdjustEndSlider)

        # Add sliders layout to the main layout
        layout.addLayout(slider_layout)

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
        units = self.dataMixin.units[self.controller.channel] if show_units else ""

        if not len(data):
            self.meanLabel.setText(f"Mean: -- {units}")
            self.stdLabel.setText(f"σ: -- {units}")
            self.minLabel.setText(f"Min: -- {units}")
            self.maxLabel.setText(f"Max: -- {units}")
            return

        mean = np.mean(data)
        std = np.std(data)
        min_val = np.min(data)
        max_val = np.max(data)

        self.meanLabel.setText(f"Mean: {mean:.2f} {units}")
        self.stdLabel.setText(f"σ: {std:.2f} {units}")
        self.minLabel.setText(f"Min: {min_val:.2f} {units}")
        self.maxLabel.setText(f"Max: {max_val:.2f} {units}")


class PlotMixin:

    def __init__(self):
        super().__init__()
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)

    def getCanvas(self):
        if not hasattr(self, 'canvas'):
            self.__init__()
        return self.canvas

    def updatePlot(self):
        try:
            self.plot()
        except Exception as e:
            # Print the exception details with traceback
            print("Exception occurred:")
            traceback.print_exc()
            self.figure.text(0.5, 0.5, "Invalid parameters",
                             fontsize=14, ha='center', va='center')
            self.canvas.draw()

    def getPlotImage(self):
        buf = io.BytesIO()
        self.figure.savefig(buf, format="png")
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
