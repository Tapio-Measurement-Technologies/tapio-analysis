from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QSizePolicy, QFileDialog, QHeaderView,
                             QLabel, QCheckBox, QPushButton)
from utils.measurement import Measurement
from utils.analysis import AnalysisControllerBase, AnalysisWindowBase
from utils.types import AnalysisType, PlotAnnotation
from utils.filters import bandpass_filter
from gui.components import ChannelMixin, BandPassFilterMixin, ExtraQLabeledDoubleRangeSlider
from matplotlib.backend_bases import MouseButton
import settings
import json

analysis_name = "Find samples"
analysis_types = ["MD"]
allow_multiple_instances = False
PEAK_WHEEL_STEP_M = 0.001


class AnalysisController(AnalysisControllerBase):
    band_pass_low: float
    band_pass_high: float
    min_length: float
    max_length: float

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD", annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__(measurement, window_type, annotations, attributes)

        self.threshold = self.measurement.threshold
        self.peaks = self.measurement.peak_locations
        self.channel = self.measurement.peak_channel or self.measurement.channels[0]
        self.selected_samples = self.measurement.selected_samples
        self.threshold_line = None
        self.peak_lines = []
        self.peak_spans = []
        self.highlighted_intervals = []
        self.zoomed_in = False
        self.invert_data = False

        self.set_default(
            'band_pass_low', settings.FIND_SAMPLES_BAND_PASS_LOW_DEFAULT_1M)
        self.set_default('band_pass_high',
                         settings.FIND_SAMPLES_BAND_PASS_HIGH_DEFAULT_1M)
        self.set_default('min_length', settings.CD_SAMPLE_MIN_LENGTH_M)
        self.set_default('max_length', settings.CD_SAMPLE_MAX_LENGTH_M)

    def plot(self):
        self.figure.clear()

        ax = self.figure.add_subplot(111)
        ax.set_title(f"{self.measurement.measurement_label} ({self.channel})")
        ax.set_xlabel("Distance [m]")
        ax.set_ylabel(
            f"{self.channel} [{self.measurement.units[self.channel]}]")

        self.distances = self.measurement.distances
        self.data = self.measurement.channel_df[self.channel]

        self.filtered_data = bandpass_filter(
            self.data, self.band_pass_low, self.band_pass_high, self.fs)

        if self.invert_data:
            self.filtered_data = -1 * self.filtered_data

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
        ax = self.figure.gca()
        self.canvas.draw_idle()

        for artist in self.peak_lines + self.peak_spans:
            artist.remove()
        self.peak_lines = []
        self.peak_spans = []

        if not self.peaks:
            return

        tape_half_width_m = settings.TAPE_WIDTH_MM / 2000.0
        for peak in self.peaks:
            tape_span = ax.axvspan(
                peak - tape_half_width_m,
                peak + tape_half_width_m,
                color='tab:red',
                alpha=0.18,
                zorder=1,
            )
            self.peak_spans.append(tape_span)

            # Draw the tape edges and the peak center
            vl = ax.axvline(x=peak, color='g', linestyle=':', zorder=3)
            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak-tape_half_width_m,
                            color='tab:red', linestyle='--', alpha=0.4, zorder=2)

            self.peak_lines.append(vl)
            vl = ax.axvline(x=peak+tape_half_width_m,
                            color='tab:red', linestyle='--', alpha=0.4, zorder=2)
            self.peak_lines.append(vl)

    def detect_peaks(self, channel):
        if self.threshold is None:
            return self.peaks

        x = self.measurement.distances
        y = self.measurement.channel_df[channel]

        # TODO: already use the filtered data in the plot method
        y = bandpass_filter(y, self.band_pass_low,
                            self.band_pass_high, self.fs)

        if self.invert_data:
            y = -1 * y

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
                    if last_peak_end is None or (min_length_meters <= (x[start] - x[last_peak_end])):
                        peaks.append(center)
                    last_peak_end = end
                    start = None

        self.peaks = peaks
        self.measurement.peak_locations = self.peaks.copy()
        self.measurement.threshold = self.threshold
        self.measurement.peak_channel = channel

        return peaks

    def get_peak_bounds(self, index):
        epsilon = 1e-6
        lower_bound = self.measurement.distances[0] if len(
            self.measurement.distances) else None
        upper_bound = self.measurement.distances[-1] if len(
            self.measurement.distances) else None

        if index > 0:
            lower_bound = self.peaks[index - 1] + epsilon
        if index < len(self.peaks) - 1:
            upper_bound = self.peaks[index + 1] - epsilon

        return lower_bound, upper_bound

    def set_peak_position(self, index, position):
        if index < 0 or index >= len(self.peaks):
            return False

        lower_bound, upper_bound = self.get_peak_bounds(index)
        if lower_bound is not None:
            position = max(position, lower_bound)
        if upper_bound is not None:
            position = min(position, upper_bound)

        self.peaks[index] = position
        self.measurement.peak_locations = self.peaks.copy()
        return True

    def move_peak(self, index, delta):
        if index < 0 or index >= len(self.peaks):
            return False
        return self.set_peak_position(index, self.peaks[index] + delta)

    def remove_peak(self, index):
        if index < 0 or index >= len(self.peaks):
            return False

        del self.peaks[index]
        self.measurement.peak_locations = self.peaks.copy()
        return True

    def get_nearest_peak_index(self, x_position):
        if x_position is None or not self.peaks:
            return None

        return min(
            range(len(self.peaks)),
            key=lambda peak_index: abs(self.peaks[peak_index] - x_position),
        )

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

class AnalysisWindow(AnalysisWindowBase[AnalysisController], ChannelMixin, BandPassFilterMixin):
    def __init__(self, controller: AnalysisController, window_type: AnalysisType = "MD"):
        super().__init__(controller, window_type)
        self.original_view_limits = None
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
        self.resize(*settings.FIND_SAMPLES_WINDOW_SIZE)

        self.initMenuBar()

        # Add the channel selector
        # Ensure this method is correctly defined elsewhere
        self.addChannelSelector(self.main_layout)
        self.addBandPassRangeSlider(self.main_layout)

        # Add invert data checkbox
        self.invertCheckbox = QCheckBox("Invert data")
        self.invertCheckbox.setChecked(self.controller.invert_data)
        self.invertCheckbox.stateChanged.connect(self.onInvertDataChanged)
        self.main_layout.addWidget(self.invertCheckbox)

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
        self.controller.canvas.mpl_connect('scroll_event', self.on_scroll)
        self.configure_home_button()

        # Table for displaying peaks
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setHorizontalHeaderLabels(
            ["Sample length [m]", "Tape center [m]", "Remove"])
        # Connect the selection change signal
        self.table.currentCellChanged.connect(self.onTableRowSelected)
        self.table.cellDoubleClicked.connect(self.onTableCellDoubleClicked)

        self.table.itemChanged.connect(self.onTableItemChanged)

        # Set the size policy to prevent the table from expanding beyond its content
        sizePolicy = QSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.table.setSizePolicy(sizePolicy)
        self.table.setMinimumWidth(420)

        # To center the table in its layout, you might need to add stretch factors to the layout
        # Add stretch before the table to push it to the center
        # layout.addStretch(1)
        layout.addWidget(self.table)
        # layout.addStretch(1)  # Add stretch after the table as well

        self.update_table()
        self.refresh()

    def onTableItemChanged(self, item):
        if item.column() == 0:
            self.measurement.selected_samples = self.get_selected_samples()
            self.controller.selected_samples = self.measurement.selected_samples.copy()
            self.refresh()
        elif item.column() == 1:
            self.update_peak_from_table(item.row(), item.text())

    def get_selected_samples(self):
        include_samples = []
        sample_rows = max(len(self.controller.peaks) - 1, 0)
        for row in range(sample_rows):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                include_samples.append(row)
        return include_samples

    def configure_home_button(self):
        toolbar = self.controller.toolbar
        toolbar.home = self.on_home_clicked

        home_action = getattr(toolbar, "_actions", {}).get("home")
        if home_action is not None:
            try:
                home_action.triggered.disconnect()
            except TypeError:
                pass
            home_action.triggered.connect(self.on_home_clicked)

    def refresh(self, update_home_limits=True):
        self.controller.updatePlot()
        if update_home_limits:
            self.original_view_limits = self.get_current_view_limits()

    def normalize_selected_samples(self, selected_samples):
        max_sample_index = max(len(self.controller.peaks) - 1, 0)
        return sorted({
            sample_index for sample_index in selected_samples
            if 0 <= sample_index < max_sample_index
        })

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

    def sync_after_peak_change(self, preserve_view=False):
        view_limits = self.get_current_view_limits() if preserve_view else None
        self.measurement.peak_locations = self.controller.peaks.copy()
        self.measurement.selected_samples = self.normalize_selected_samples(
            self.measurement.selected_samples)
        self.controller.selected_samples = self.measurement.selected_samples.copy()

        if len(self.controller.peaks) >= 2:
            self.measurement.split_data_to_segments()
        else:
            self.measurement.segments = {}
            self.measurement.cd_distances = []

        self.update_table()
        self.refresh(update_home_limits=not preserve_view)
        self.restore_view_limits(view_limits)

    def update_peak_from_table(self, peak_index, value):
        try:
            peak_position = float(value)
        except ValueError:
            self.update_table()
            return

        self.controller.set_peak_position(peak_index, peak_position)
        self.sync_after_peak_change()

    def remap_selected_samples_after_peak_removal(self, removed_peak_index):
        peak_count_before_removal = len(self.controller.peaks)
        last_peak_index = peak_count_before_removal - 1
        remapped_samples = []

        for sample_index in self.measurement.selected_samples:
            if removed_peak_index == 0:
                if sample_index == 0:
                    continue
                remapped_samples.append(sample_index - 1)
            elif removed_peak_index == last_peak_index:
                if sample_index == removed_peak_index - 1:
                    continue
                remapped_samples.append(sample_index)
            else:
                if sample_index == removed_peak_index:
                    continue
                if sample_index > removed_peak_index:
                    remapped_samples.append(sample_index - 1)
                else:
                    remapped_samples.append(sample_index)

        return self.normalize_selected_samples(remapped_samples)

    def on_remove_peak(self, peak_index):
        if peak_index < 0 or peak_index >= len(self.controller.peaks):
            return

        self.measurement.selected_samples = self.remap_selected_samples_after_peak_removal(
            peak_index)
        self.controller.remove_peak(peak_index)
        self.sync_after_peak_change()

    def is_navigation_mode_active(self):
        return bool(
            self.controller.canvas.toolbar and self.controller.canvas.toolbar.mode
        )

    def on_click(self, event):
        if event.inaxes not in self.controller.figure.axes:
            return

        if self.is_navigation_mode_active():
            return

        if event.button == settings.FREQUENCY_SELECTOR_MOUSE_BUTTON:  # Middle mouse button
            if event.ydata is not None:
                self.controller.highlighted_intervals = []
                self.controller.threshold = event.ydata
                self.measurement.peak_channel = self.controller.channel
                self.controller.detect_peaks(self.controller.channel)
                self.measurement.selected_samples = self.get_selected_samples()
                self.controller.selected_samples = self.measurement.selected_samples.copy()
                self.update_table(select_all=True)
                self.measurement.selected_samples = self.get_selected_samples()
                self.controller.selected_samples = self.measurement.selected_samples.copy()
                self.measurement.split_data_to_segments()
                self.refresh()
            return

        if event.button == MouseButton.LEFT and event.xdata is not None:
            nearest_peak_index = self.controller.get_nearest_peak_index(event.xdata)
            if nearest_peak_index is None:
                return

            self.controller.set_peak_position(nearest_peak_index, event.xdata)
            self.sync_after_peak_change(preserve_view=True)

    def on_scroll(self, event):
        if event.xdata is None or event.inaxes not in self.controller.figure.axes:
            return

        if self.is_navigation_mode_active():
            return

        nearest_peak_index = self.controller.get_nearest_peak_index(event.xdata)
        if nearest_peak_index is None:
            return

        self.controller.move_peak(nearest_peak_index, PEAK_WHEEL_STEP_M * event.step)
        self.sync_after_peak_change(preserve_view=True)

    def onInvertDataChanged(self, state):
        # PyQt6 stateChanged emits int (0/2), so compare against enum value.
        self.controller.invert_data = (state == Qt.CheckState.Checked.value)
        # Invert is a local view toggle only; sample detection is only triggered on click.
        self.refresh()

    def update_table(self, select_all=False):
        self.table.blockSignals(True)
        self.table.clearContents()

        peak_count = len(self.controller.peaks)
        self.table.setRowCount(peak_count)

        for i, peak in enumerate(self.controller.peaks):
            if i < peak_count - 1:
                chk_box_item = QTableWidgetItem()
                chk_box_item.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled |
                    Qt.ItemFlag.ItemIsSelectable
                )
                sample_length = (
                    self.controller.peaks[i + 1] - self.controller.peaks[i]) - (settings.TAPE_WIDTH_MM / 1000)
                if sample_length > self.controller.max_length:
                    chk_box_item.setCheckState(Qt.CheckState.Unchecked)
                elif (i in self.measurement.selected_samples) or select_all:
                    chk_box_item.setCheckState(Qt.CheckState.Checked)
                else:
                    chk_box_item.setCheckState(Qt.CheckState.Unchecked)
                chk_box_item.setText(f"{sample_length:.2f}")
            else:
                chk_box_item = QTableWidgetItem("")
                chk_box_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            self.table.setItem(i, 0, chk_box_item)

            peak_item = QTableWidgetItem(f"{peak:.3f}")
            peak_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled |
                Qt.ItemFlag.ItemIsSelectable |
                Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(i, 1, peak_item)

            remove_button = QPushButton("Remove")
            remove_button.clicked.connect(
                lambda _, peak_index=i: self.on_remove_peak(peak_index))
            self.table.setCellWidget(i, 2, remove_button)

        self.measurement.selected_samples = self.get_selected_samples()
        self.controller.selected_samples = self.measurement.selected_samples.copy()
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
        if 0 <= row < len(self.controller.peaks) - 1:
            selected_interval = (
                self.controller.peaks[row], self.controller.peaks[row + 1])
            self.controller.highlight_intervals([selected_interval])
        else:
            self.controller.highlight_intervals([])

    def onTableCellDoubleClicked(self, row, column):
        if row < len(self.controller.peaks) - 1:
            start = self.controller.peaks[row]
            end = self.controller.peaks[row + 1]
            self.controller.zoom_to_interval(start, end)

    def onSampleLengthChanged(self):
        low, high = self.sampleLengthSlider.value()
        self.controller.min_length = low
        self.controller.max_length = high
        self.update_table()
        self.refresh()

    def on_home_clicked(self, *args):
        self.restore_view_limits(self.original_view_limits)
