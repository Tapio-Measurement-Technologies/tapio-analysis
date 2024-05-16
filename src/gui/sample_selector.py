from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QScrollArea, QWidget
from PyQt6.QtCore import pyqtSignal, Qt
from utils.data_loader import DataMixin


class SampleSelectorWindow(QWidget, DataMixin):

    closed = pyqtSignal()

    def __init__(self, samples, change_handler):
        super().__init__()
        # This should be a list of dictionaries, with each dict representing a sample

        self.dataMixin = DataMixin.getInstance()
        self.samples = samples
        self.change_handler = change_handler
        self.initUI()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def initUI(self):
        self.setWindowTitle("Select Samples")
        self.setGeometry(100, 100, 300, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Scroll area setup
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scrollContent = QWidget(scroll)
        scrollLayout = QVBoxLayout(scrollContent)
        scrollContent.setLayout(scrollLayout)

        for sample_index in range(len(next(iter(self.dataMixin.segments.values())))):
            checkbox = QCheckBox(f"{1+sample_index}")
            checkbox.setChecked(sample_index in self.samples)
            checkbox.stateChanged.connect(
                lambda state, s=sample_index: self.onCheckboxStateChanged(state, s))
            scrollLayout.addWidget(checkbox)

        scrollLayout.addStretch(1)
        scroll.setWidget(scrollContent)
        layout.addWidget(scroll)

    def onCheckboxStateChanged(self, state, sample_index):
        if state == Qt.CheckState.Checked.value and sample_index not in self.samples:
            self.samples.append(sample_index)
        elif state == Qt.CheckState.Unchecked.value and sample_index in self.samples:
            self.samples.remove(sample_index)
        self.change_handler(self.samples)
