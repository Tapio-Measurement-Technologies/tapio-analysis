from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QSizePolicy, QFileDialog, QHeaderView,
                             QLabel)
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.filters import bandpass_filter
from gui.components import ChannelMixin, BandPassFilterMixin, ExtraQLabeledDoubleRangeSlider
import settings
import json

analysis_name = "Find samples"
analysis_types = ["MD"]
allow_multiple_instances = False

class AnalysisController(AnalysisControllerBase):
    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.threshold = self.measurement.threshold
        self.peaks = self.measurement.peak_locations
        self.channel = self.measurement.peak_channel or self.measurement.channels[0]
        self.selected_samples = self.measurement.selected_samples
        self.threshold_line = None
        self.peak_lines = []
        self.fs = 1 / self.measurement.sample_step
        self.highlighted_intervals = []
        self.zoomed_in = False

        self.set_default('band_pass_low', settings.FIND_SAMPLES_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high', settings.FIND_SAMPLES_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('min_length', settings.CD_SAMPLE_MIN_LENGTH_M)
        self.set_default('max_length', settings.CD_SAMPLE_MAX_LENGTH_M)

    def plot(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        self.distances = self.measurement.distances
        self.data = self.measurement.channel_df[self.channel]

        self.filtered_data = bandpass_filter(
            self.data, self.band_pass_low, self.band_pass_high, self.fs)

        alpha = 0.4 if len(self.measurement.selected_samples) else 1
        # Draw the entire data line with lower alpha
        ax.plot(self.distances, self.filtered_data,
                color='tab:blue', alpha=alpha)

        # Highlight the selected samples
        for i in self.measurement.selected_samples:
            if i < len(self.peaks) - 1:
                start = self.peaks[i]
                end = self.peaks[i + 1]
                mask = (self.distances >= start) & (self.distances <= end)
                ax.plot(
                    self.distances[mask], self.filtered_data[mask], color='tab:blue', alpha=1.0)

        ax.set_title(f"{self.measurement.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(f"{self.channel} [{self.measurement.units[self.channel]}]")

        self.draw_peaks()
        if self.channel == self.measurement.peak_channel:
            self.draw_threshold()

        # Highlight selected intervals
        if not self.zoomed_in:
            for start, end in self.highlighted_intervals:
                ax.axvspan(start, end, color='black', alpha=0.1)

        self.zoomed_in = False

        self.canvas.draw()
        self.updated.emit()

        return self.canvas

    def draw_threshold(self):
        if self.threshold:
            ax = self.figure.gca()
            if self.threshold_line:
                self.threshold_line.remove()
            self.threshold_line = ax.axhline(
                y=self.threshold, color='r', linestyle='--')

    def draw_peaks(self):
        if not self.peaks:
            return
        # Plots the self.peaks
        ax = self.figure.gca()
        self.canvas.draw_idle()

        [i.remove() for i in self.peak_lines]
        self.peak_lines = []

        for peak in self.peaks:
            # Draw the tape edges and the peak center
            vl = ax.axvline(x=peak, color='g', linestyle=':')
            tape_width_m = settings.TAPE_WIDTH_MM / 1000.0

            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak-tape_width_m,
                            color='tab:red', linestyle='--', alpha=0.2)

            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak+tape_width_m,
                            color='tab:red', linestyle='--', alpha=0.2)
            self.peak_lines.append(vl)

    def detect_peaks(self, channel):
        x = self.measurement.distances
        y = self.measurement.channel_df[channel]

        # TODO: already use the filtered data in the plot method
        y = bandpass_filter(y, self.band_pass_low,
                            self.band_pass_high, self.fs)

        peaks = []
        start = None

        tape_width_meters = settings.TAPE_WIDTH_MM / 1000.0
        min_length_meters = self.min_length
        max_length_meters = self.max_length
        print("min: ", min_length_meters, " max: ", max_length_meters)

        last_peak_end = None

        for i in range(len(y)):
            if y[i] > self.threshold and start is None:
                start = i
            elif (y[i] <= self.threshold or i == len(y) - 1) and start is not None:
                end = i
                if start is not None and (x[end] - x[start]) >= tape_width_meters:
                    center = x[start] + (x[end] - x[start]) / 2

                    # Check if this is the first peak or if the distance from last peak is within bounds
                    if last_peak_end is None or (
                        min_length_meters <= (
                            x[start] - x[last_peak_end]) <= max_length_meters
                    ):
                        peaks.append(center)
                        last_peak_end = end
                    start = None

        self.peaks = peaks
        self.measurement.peak_locations = self.peaks
        self.measurement.threshold = self.threshold
        self.measurement.peak_channel = channel

        return peaks

    def highlight_intervals(self, intervals):
        self.highlighted_intervals = intervals
        self.plot()  # Redraw the main plot

    def zoom_to_interval(self, start, end):
        tape_width_meters = settings.TAPE_WIDTH_MM / 1000.0
        self.zoomed_in = True
        self.plot()
        ax = self.figure.gca()
        ax.set_xlim(start + tape_width_meters / 2, end - tape_width_meters / 2)
        self.canvas.draw()


class CustomNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent):
        super().__init__(canvas, parent)
        self.parent = parent

    def home(self):
        # Override home button functionality to reset the view
        self.parent.refresh()


class AnalysisWindow(AnalysisWindowBase[AnalysisController], ChannelMixin, BandPassFilterMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.initUI()

    def initMenuBar(self):
        saveAction = QAction('&Save samples', self)
        saveAction.setShortcut('Ctrl+S')
        saveAction.setStatusTip('Save sample indexes to a JSON file')
        saveAction.triggered.connect(self.save_samples)
        self.file_menu.addAction(saveAction)

    def initUI(self):
        self.setWindowTitle(
            f"Find CD Samples ({self.measurement.measurement_label})")

        self.setGeometry(100, 100, 1000, 800)

        self.initMenuBar()

        # Add the channel selector
        # Ensure this method is correctly defined elsewhere
        self.addChannelSelector(self.main_layout)
        self.addBandPassRangeSlider(self.main_layout)

        # Add sample length range slider
        sampleLengthLabel = QLabel("Sample length range [m]")
        self.main_layout.addWidget(sampleLengthLabel)

        self.sampleLengthSlider = ExtraQLabeledDoubleRangeSlider(
            Qt.Orientation.Horizontal)
        self.sampleLengthSlider.setDecimals(2)
        self.sampleLengthSlider.setRange(settings.CD_SAMPLE_LENGTH_SLIDER_MIN,
                                         settings.CD_SAMPLE_LENGTH_SLIDER_MAX)
        self.sampleLengthSlider.setValue((settings.CD_SAMPLE_MIN_LENGTH_M,
                                          settings.CD_SAMPLE_MAX_LENGTH_M))
        self.sampleLengthSlider.sliderReleased.connect(
            self.onSampleLengthChanged)
        self.sampleLengthSlider.editingFinished.connect(
            self.onSampleLengthChanged)

        self.main_layout.addWidget(self.sampleLengthSlider)

        layout = QHBoxLayout()
        self.main_layout.addLayout(layout)

        # Plot layout
        plotLayout = QVBoxLayout()
        layout.addLayout(plotLayout)

        self.controller.addPlot(plotLayout)
        self.controller.canvas.mpl_connect('button_press_event', self.on_click)

        # Table for displaying peaks
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(["Sample length [m]"])
        # Connect the selection change signal
        self.table.currentCellChanged.connect(self.onTableRowSelected)
        self.table.cellDoubleClicked.connect(self.onTableCellDoubleClicked)

        self.table.itemChanged.connect(self.onTableItemChanged)

        # Set the size policy to prevent the table from expanding beyond its content
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.table.setSizePolicy(sizePolicy)

        # To center the table in its layout, you might need to add stretch factors to the layout
        # Add stretch before the table to push it to the center
        # layout.addStretch(1)
        layout.addWidget(self.table)
        # layout.addStretch(1)  # Add stretch after the table as well

        self.refresh()

    def onTableItemChanged(self, item):
        # Perform action only for checkbox state changes, if necessary
        if item.column() == 0:  # Assuming checkboxes are in the first column
            include_samples = self.get_selected_samples()
            self.measurement.selected_samples = include_samples
            self.refresh()

    def get_selected_samples(self):
        include_samples = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:
                include_samples.append(row)
        return include_samples

    def refresh(self):
        self.controller.updatePlot()

    def on_click(self, event):
        if event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:  # Middle mouse button
            if event.ydata is not None:
                self.controller.highlighted_intervals = []
                self.controller.threshold = event.ydata
                self.measurement.peak_channel = self.controller.channel
                self.controller.detect_peaks(self.controller.channel)
                self.update_table(select_all=True)
                self.measurement.selected_samples = self.get_selected_samples()
                self.measurement.split_data_to_segments()
                self.refresh()

    def update_table(self, select_all=False):
        if not self.controller.peaks:
            return
        self.table.blockSignals(True)

        self.table.setRowCount(len(self.controller.peaks) - 1)

        for i in range(len(self.controller.peaks) - 1):
            # Checkbox for inclusion
            chk_box_item = QTableWidgetItem()
            chk_box_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            if (i in self.controller.selected_samples) or select_all:
                chk_box_item.setCheckState(Qt.CheckState.Checked)
            else:
                chk_box_item.setCheckState(Qt.CheckState.Unchecked)
            sample_length = (
                self.controller.peaks[i + 1] - self.controller.peaks[i]) - (settings.TAPE_WIDTH_MM / 1000)
            chk_box_item.setText(f"{sample_length:.2f}")
            self.table.setItem(i, 0, chk_box_item)

        self.table.blockSignals(False)

    def save_samples(self):
        # Open file dialog to choose where to save the JSON file
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileName, _ = QFileDialog.getSaveFileName(self, "Save File", "",
                                                  "Sample JSON Files (*.samples.json);;All Files (*)", options=options)
        if fileName:

            samples_data = {"peak_locations": self.measurement.peak_locations,
                            "peak_channel": self.measurement.peak_channel,
                            "threshold": self.measurement.threshold,
                            "selected_samples": self.measurement.selected_samples
                            }
            with open(fileName, 'w') as file:
                json.dump(samples_data, file, indent=4)

    def onTableRowSelected(self, row, column):
        if row < len(self.controller.peaks) - 1:
            selected_interval = (
                self.controller.peaks[row], self.controller.peaks[row + 1])
            self.controller.highlight_intervals([selected_interval])

    def onTableCellDoubleClicked(self, row, column):
        if row < len(self.controller.peaks) - 1:
            start = self.controller.peaks[row]
            end = self.controller.peaks[row + 1]
            self.controller.zoom_to_interval(start, end)

    def onSampleLengthChanged(self):
        low, high = self.sampleLengthSlider.value()
        self.controller.min_length = low
        self.controller.max_length = high
