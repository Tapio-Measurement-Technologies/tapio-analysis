from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QSizePolicy, QMenuBar, QFileDialog, QHeaderView)
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import settings
from utils.data_loader import DataMixin
from gui.components import ChannelMixin, BandPassFilterMixin
from controllers import FindSamplesController

class CustomNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent):
        super().__init__(canvas, parent)
        self.parent = parent

    def home(self):
        # Override home button functionality to reset the view
        self.parent.refresh()

class FindSamplesWindow(QWidget, DataMixin, ChannelMixin, BandPassFilterMixin):
    closed = pyqtSignal()

    def __init__(self, controller: FindSamplesController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else FindSamplesController()
        self.isClosed = False
        self.initUI()

    def closeEvent(self, event):
        self.isClosed = True
        self.closed.emit()
        super().closeEvent(event)

    def initUI(self):
        self.setWindowTitle(
            f"Find CD Samples ({self.dataMixin.measurement_label})")

        self.setGeometry(100, 100, 1000, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)

        # Create the menu bar
        menuBar = QMenuBar(self)
        fileMenu = menuBar.addMenu('&File')

        # Add "Save" action to the "File" menu
        saveAction = QAction('&Save samples', self)
        saveAction.setShortcut('Ctrl+S')
        saveAction.setStatusTip('Save sample indexes to a JSON file')
        saveAction.triggered.connect(self.save_samples)

        fileMenu.addAction(saveAction)

        mainLayout.setMenuBar(menuBar)  # Add the menu bar to the main layout

        # Add the channel selector
        # Ensure this method is correctly defined elsewhere
        self.addChannelSelector(mainLayout)
        self.addBandPassRangeSlider(mainLayout)

        layout = QHBoxLayout()
        mainLayout.addLayout(layout)

        # Plot layout
        plotLayout = QVBoxLayout()
        layout.addLayout(plotLayout)

        self.plot = self.controller.getCanvas()
        self.plot.mpl_connect('button_press_event', self.on_click)
        plotLayout.addWidget(self.plot, 1)

        self.toolbar = CustomNavigationToolbar(self.plot, self)
        plotLayout.addWidget(self.toolbar)

        # Table for displaying peaks
        self.table = QTableWidget()
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels(["Sample length [m]"])
        self.table.currentCellChanged.connect(self.onTableRowSelected)  # Connect the selection change signal
        self.table.cellDoubleClicked.connect(self.onTableCellDoubleClicked)

        self.table.itemChanged.connect(self.onTableItemChanged)

        # Set the size policy to prevent the table from expanding beyond its content
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.table.setSizePolicy(sizePolicy)

        # Optionally, you can set a fixed width for the column, e.g., 200 pixels
        self.table.setColumnWidth(0, 100)

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
            self.dataMixin.selected_samples = include_samples

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
        if event.button == 2:  # Middle mouse button
            if event.ydata is not None:
                self.controller.threshold = event.ydata
                self.dataMixin.peak_channel = self.controller.channel
                self.controller.detect_peaks(self.controller.channel)
                self.update_table(select_all=True)
                self.dataMixin.selected_samples = self.get_selected_samples()
                self.dataMixin.split_data_to_segments()
                self.refresh()

    def update_table(self, select_all=False):
        if not self.controller.peaks:
            return
        self.table.blockSignals(True)

        self.table.setRowCount(len(self.controller.peaks) - 1)

        for i in range(len(self.controller.peaks) - 1):
            # Checkbox for inclusion
            chk_box_item = QTableWidgetItem()
            chk_box_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
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

            samples_data = {"peak_locations": self.dataMixin.peak_locations,
                            "peak_channel": self.dataMixin.peak_channel,
                            "threshold": self.dataMixin.threshold,
                            "selected_samples": self.dataMixin.selected_samples
                            }
            with open(fileName, 'w') as file:
                json.dump(samples_data, file, indent=4)

    def onTableRowSelected(self, row, column):
        if row < len(self.controller.peaks) - 1:
            selected_interval = (self.controller.peaks[row], self.controller.peaks[row + 1])
            self.controller.highlight_intervals([selected_interval])

    def onTableCellDoubleClicked(self, row, column):
        if row < len(self.controller.peaks) - 1:
            start = self.controller.peaks[row]
            end = self.controller.peaks[row + 1]
            self.controller.zoom_to_interval(start, end)
