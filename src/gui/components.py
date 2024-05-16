from PyQt6.QtWidgets import QComboBox, QLabel, QDoubleSpinBox, QFileDialog
from PyQt6.QtGui import QAction
from qtpy.QtCore import Qt, Signal
from superqt import QLabeledDoubleRangeSlider, QLabeledSlider

import logging
import settings
import numpy as np

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

    def addMachineSpeedSpinner(self, layout):
        self.machineSpeedLabel = QLabel("Machine Speed [m/min]:")
        layout.addWidget(self.machineSpeedLabel)
        self.machineSpeedSpinBox = QDoubleSpinBox()

        self.machineSpeedSpinBox.setMinimum(0.0)
        self.machineSpeedSpinBox.setMaximum(3000)
        self.machineSpeedSpinBox.setSingleStep(0.1)
        self.machineSpeedSpinBox.setValue(self.controller.machine_speed)
        layout.addWidget(self.machineSpeedSpinBox)
        self.machineSpeedSpinBox.valueChanged.connect(self.machineSpeedChanged)

    def machineSpeedChanged(self, value):
        self.controller.machine_speed = value
        self.refresh()


class FrequencyRangeMixin:

    def addFrequencyRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.frequencyRangeLabel = QLabel("Frequency range [1/m]")
        layout.addWidget(self.frequencyRangeLabel)
        self.frequencyRangeSlider = ExtraQLabeledDoubleRangeSlider(Qt.Orientation.Horizontal)
        self.frequencyRangeSlider.setDecimals(1)
        self.frequencyRangeSlider.setRange(0, self.controller.max_freq)
        self.frequencyRangeSlider.setValue((self.controller.frequency_range_low, self.controller.frequency_range_high))

        if live_update:
            self.frequencyRangeSlider.valueChanged.connect(self.frequencyRangeChanged)
        else:
            self.frequencyRangeSlider.sliderReleased.connect(self.frequencyRangeChanged)
            self.frequencyRangeSlider.editingFinished.connect(self.frequencyRangeChanged)
        layout.addWidget(self.frequencyRangeSlider)

    def frequencyRangeChanged(self):
        self.controller.frequency_range_low, self.controller.frequency_range_high = self.frequencyRangeSlider.value()
        self.refresh()  # Optionally refresh the plot if needed

class AnalysisRangeMixin:

    def addAnalysisRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.analysisRangeLabel = QLabel("Analysis range [m]")
        layout.addWidget(self.analysisRangeLabel)
        self.analysisRangeSlider = ExtraQLabeledDoubleRangeSlider(Qt.Orientation.Horizontal)
        self.analysisRangeSlider.setDecimals(1)
        # Ensure dataMixin is accessible
        # self.max_dist = np.max(self.dataMixin.distances)
        self.analysisRangeSlider.setRange(0, self.controller.max_dist)
        self.analysisRangeSlider.setValue((self.controller.analysis_range_low, self.controller.analysis_range_high))

        if live_update:
            self.analysisRangeSlider.valueChanged.connect(self.analysisRangeChanged)
        else:
            self.analysisRangeSlider.sliderReleased.connect(self.analysisRangeChanged)
            self.analysisRangeSlider.editingFinished.connect(self.analysisRangeChanged)
        layout.addWidget(self.analysisRangeSlider)

    def analysisRangeChanged(self):
        self.controller.analysis_range_low, self.controller.analysis_range_high = self.analysisRangeSlider.value()
        self.refresh()


class ChannelMixin:

    def addChannelSelector(self, layout):
        self.channelComboBox = QComboBox()
        self.channelComboBox.addItems(self.dataMixin.channels)
        initial_channel = self.controller.channel

        if initial_channel is not None and initial_channel in self.dataMixin.channels:
            initial_index = self.channelComboBox.findText(initial_channel)
            if initial_index >= 0:  # Ensure the text was found
                self.channelComboBox.setCurrentIndex(initial_index)

        layout.addWidget(self.channelComboBox)
        self.channelComboBox.currentIndexChanged.connect(self.channelChanged)

    def channelChanged(self):
        self.controller.channel = self.channelComboBox.currentText()
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


    def addSpectrumLengthSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        self.spectrumLengthSlider = ExtraQLabeledSlider(Qt.Orientation.Horizontal)
        self.spectrumLengthSlider.setMinimum(self.controller.spectrum_length_slider_min)
        self.spectrumLengthSlider.setMaximum(self.controller.spectrum_length_slider_max)
        self.spectrumLengthSlider.setSingleStep(1000)
        self.spectrumLengthSlider.setValue(self.controller.nperseg)
        layout.addWidget(self.spectrumLengthSlider)

        if live_update:
            self.spectrumLengthSlider.valueChanged.connect(self.spectrumLengthChanged)
        else:
            self.spectrumLengthSlider.sliderReleased.connect(self.spectrumLengthChanged)
            self.spectrumLengthSlider.editingFinished.connect(self.spectrumLengthChanged)

    def spectrumLengthChanged(self):
        self.controller.nperseg = self.spectrumLengthSlider.value()  # Update your nperseg value based on the slider
        self.refresh()  # Refresh the plot with the new spectrum length


class BandPassFilterMixin:

    def bandPassFilterRangeChanged(self):
        self.controller.band_pass_low, self.controller.band_pass_high = self.bandPassFilterSlider.value()
        self.refresh()

    def addBandPassRangeSlider(self, layout, live_update=settings.UPDATE_ON_SLIDE):
        # Band pass filter range slider
        self.bandPassFilterLabel = QLabel("Band pass filter [1/m]")
        layout.addWidget(self.bandPassFilterLabel)
        self.bandPassFilterSlider = ExtraQLabeledDoubleRangeSlider(Qt.Orientation.Horizontal)
        self.bandPassFilterSlider.setRange(0, self.controller.fs / 2 - 1)
        self.bandPassFilterSlider.setValue((self.controller.band_pass_low, self.controller.band_pass_high))

        if live_update:
            self.bandPassFilterSlider.valueChanged.connect(self.bandPassFilterRangeChanged)
        else:
            self.bandPassFilterSlider.sliderReleased.connect(self.bandPassFilterRangeChanged)
            self.bandPassFilterSlider.editingFinished.connect(self.bandPassFilterRangeChanged)

        layout.addWidget(self.bandPassFilterSlider)

        self.bandPassFilterSlider.setTracking(True)


class SampleSelectMixin:

    def toggleSelectSamples(self):
        """Toggle the visibility of the sample selector window."""
        if self.sampleSelectorWindow is None:
            self.sampleSelectorWindow = SampleSelectorWindow(self.controller.selected_samples, self.selectSamples)
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


class ExportMixin:

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
        raise NotImplementedError("Subclasses should implement this method to return the data as a DataFrame.")

class StatsMixin:

    def updateStatistics(self, data, show_units=True):
        mean = np.mean(data)
        std = np.std(data)
        min_val = np.min(data)
        max_val = np.max(data)
        units = self.dataMixin.units[self.controller.channel] if show_units else ""

        self.meanLabel.setText(f"Mean: {mean:.2f} {units}")
        self.stdLabel.setText(f"σ: {std:.2f} {units}")
        self.minLabel.setText(f"Min: {min_val:.2f} {units}")
        self.maxLabel.setText(f"Max: {max_val:.2f} {units}")