from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel
from PyQt6.QtCore import pyqtSignal
from qtpy.QtCore import Qt
import numpy as np

from utils.data_loader import DataMixin


class PaperMachineDataWindow(QWidget, DataMixin):

    closed = pyqtSignal()

    def __init__(self, change_handler, window_type):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.change_handler = change_handler
        self.checkboxes = []
        self.window_type = window_type
        self.initUI()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def initUI(self):
        self.setWindowTitle(f"{self.window_type} Paper machine data")
        self.setGeometry(100, 100, 300, 500)

        self.mainLayout = QVBoxLayout()
        self.setLayout(self.mainLayout)
        self.pm_data = self.dataMixin.pm_data[self.window_type]

    def clearLayout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def populate_pm_data(self, machine_speed):
        for group in self.pm_data:
            if 'elements' in group and isinstance(group['elements'], list):
                for element in group['elements']:
                    machine_speed_at_element = machine_speed

                    if 'machine_speed' in element:
                        machine_speed_at_element = element['machine_speed']

                    if 'frequency' in element:
                        element['spatial_frequency'] = element['frequency'] / \
                            (machine_speed / 60)

                    elif 'frequency_rpm' in element:
                        element['spatial_frequency'] = element['frequency_rpm'] / \
                            (machine_speed_at_element)

                    elif 'length' in element:
                        element['spatial_frequency'] = 1 / element['length']
                    elif 'diameter' in element or 'length' in element:
                        element['spatial_frequency'] = 1 / \
                            (np.pi * element['diameter'])

                    if 'vanes' in element:
                        element['spatial_frequency'] = element['vanes'] * element['spatial_frequency']
                    element['frequency_hz'] = element['spatial_frequency'] * (machine_speed_at_element / 60)

    def refresh_pm_data(self, machine_speed):

        self.clearLayout(self.mainLayout)
        self.checkboxes.clear()
        self.populate_pm_data(machine_speed)

        for group in self.pm_data:
            groupName = group.get('groupName', 'Unnamed group')
            groupLabel = QLabel(f"<b>{groupName}</b>")

            self.mainLayout.addWidget(groupLabel)
            if 'elements' in group and isinstance(group['elements'], list):
                for element in group['elements']:

                    wavelength = 1 / element['spatial_frequency']

                    elementName = element.get('name', 'Unnamed Element')
                    if self.window_type == "MD":
                        checkbox = QCheckBox(
                            f"{elementName}: {element['spatial_frequency']:.2f} 1/m {element['frequency_hz']:.2f} Hz (λ = {wavelength:.3f} m)"
                        )
                    elif self.window_type == "CD":
                        checkbox = QCheckBox(
                            f"{elementName}: {element['spatial_frequency']:.2f} 1/m (λ = {wavelength:.3f} m)")

                    checkbox.setChecked(element.get('checked', False))
                    checkbox.setProperty('element', element)
                    checkbox.stateChanged.connect(lambda state, elem=element: self.onCheckboxStateChanged(state, elem))

                    self.mainLayout.addWidget(checkbox)
                    self.checkboxes.append(checkbox)

        self.mainLayout.addStretch(1)

    def onCheckboxStateChanged(self, state, element):
        element['checked'] = (state == Qt.CheckState.Checked.value)
        checked_elements = [checkbox.property('element') for checkbox in self.checkboxes if checkbox.isChecked()]
        self.change_handler(checked_elements)
