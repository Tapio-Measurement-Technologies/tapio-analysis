from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
import numpy as np

from utils.data_loader import DataMixin


class PaperMachineDataWindow(QWidget, DataMixin):

    closed = pyqtSignal()

    def __init__(self, change_handler, window_type):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.change_handler = change_handler
        self.checkboxes = []
        self.group_checkboxes = {}
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
        if layout is None:
            return
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            else:
                self.clearLayout(child.layout())

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
        self.group_checkboxes.clear()
        self.populate_pm_data(machine_speed)

        for group in self.pm_data:
            groupCheckboxLayout = QHBoxLayout()
            groupName = group.get('groupName', 'Unnamed group')
            groupLabel = QLabel(f"<b>{groupName}</b>")
            groupCheckbox = QCheckBox()
            self.group_checkboxes[groupCheckbox] = []

            groupCheckboxLayout.addWidget(groupCheckbox)
            groupCheckboxLayout.addWidget(groupLabel)
            groupCheckboxLayout.addStretch()
            self.mainLayout.addLayout(groupCheckboxLayout)
            groupCheckbox.stateChanged.connect(lambda state, g=group, gc=groupCheckbox: self.onGroupCheckboxStateChanged(state, g, gc))

            if 'elements' in group and isinstance(group['elements'], list):
                for element in group['elements']:
                    # Add "indentation" to element checkboxes
                    elementCheckboxLayout = QHBoxLayout()
                    elementCheckboxLayout.addSpacing(16)
                    wavelength = 1 / element['spatial_frequency']

                    elementName = element.get('name', 'Unnamed Element')
                    if self.window_type == "MD":
                        checkbox = QCheckBox(
                            f"{elementName}: {element['spatial_frequency']:.2f} 1/m {element['frequency_hz']:.2f} Hz (λ = {100*wavelength:.2f} cm)"
                        )
                    elif self.window_type == "CD":
                        checkbox = QCheckBox(
                            f"{elementName}: {element['spatial_frequency']:.2f} 1/m (λ = {100*wavelength:.2f} cm)")

                    checkbox.setChecked(element.get('checked', False))
                    checkbox.setProperty('element', element)
                    checkbox.stateChanged.connect(lambda state, elem=element, gc=groupCheckbox: self.onElementCheckboxStateChanged(state, elem, gc))

                    elementCheckboxLayout.addWidget(checkbox)
                    self.mainLayout.addLayout(elementCheckboxLayout)
                    self.checkboxes.append(checkbox)
                    self.group_checkboxes[groupCheckbox].append(checkbox)

            self.updateGroupCheckboxState(groupCheckbox)

        self.mainLayout.addStretch(1)

    def onElementCheckboxStateChanged(self, state, element, groupCheckbox):
        element['checked'] = (state == Qt.CheckState.Checked.value)
        self.updateGroupCheckboxState(groupCheckbox)
        checked_elements = [checkbox.property('element') for checkbox in self.checkboxes if checkbox.isChecked()]
        self.change_handler(checked_elements)

    def onGroupCheckboxStateChanged(self, state, group, groupCheckbox):
        if state == Qt.CheckState.PartiallyChecked:
            return

        group_elements = group.get('elements', [])
        is_checked = (state == Qt.CheckState.Checked.value)

        for element in group_elements:
            element['checked'] = is_checked

        for checkbox in self.group_checkboxes[groupCheckbox]:
            checkbox.blockSignals(True)
            checkbox.setChecked(is_checked)
            checkbox.blockSignals(False)

        checked_elements = [checkbox.property('element') for checkbox in self.checkboxes if checkbox.isChecked()]
        groupCheckbox.setTristate(False)
        self.change_handler(checked_elements)

    def updateGroupCheckboxState(self, groupCheckbox):
        elements_checkboxes = self.group_checkboxes[groupCheckbox]
        groupCheckbox.blockSignals(True)
        if all(checkbox.isChecked() for checkbox in elements_checkboxes):
            groupCheckbox.setCheckState(Qt.CheckState.Checked)
            groupCheckbox.setTristate(False)
        elif any(checkbox.isChecked() for checkbox in elements_checkboxes):
            groupCheckbox.setCheckState(Qt.CheckState.PartiallyChecked)
        else:
            groupCheckbox.setCheckState(Qt.CheckState.Unchecked)
            groupCheckbox.setTristate(False)
        groupCheckbox.blockSignals(False)
