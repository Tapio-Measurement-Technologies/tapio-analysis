from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QHBoxLayout, QToolButton, QScrollArea, QSizePolicy, QFrame, QLabel
from PyQt6.QtCore import pyqtSignal, Qt, pyqtSlot
import numpy as np

from utils.data_loader import DataMixin

COLLAPSE_BY_DEFAULT = True

class CollapsibleBox(QWidget):
    stateChanged = pyqtSignal(bool)

    def __init__(self, title="", collapsed=True, parent=None):
        super().__init__(parent)

        self.toggle_button = QToolButton(
            text=title, checkable=True, checked=collapsed
        )
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        self.content_area = QScrollArea(
            maximumHeight=0, minimumHeight=0
        )
        self.content_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.content_area.setFrameShape(QFrame.Shape.NoFrame)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

        self.set_initial_state(collapsed)

    def set_initial_state(self, collapsed):
        if not collapsed:
            self.expand()
        else:
            self.collapse()

    @pyqtSlot()
    def on_pressed(self):
        checked = self.toggle_button.isChecked()
        self.stateChanged.emit(checked)
        if not checked:
            self.expand()
        else:
            self.collapse()

    def setContentLayout(self, layout):
        lay = self.content_area.layout()
        del lay
        self.content_area.setLayout(layout)
        if self.toggle_button.isChecked():
            self.collapse()
        else:
            self.expand()

    def expand(self):
        try:
            content_height = self.content_area.layout().sizeHint().height()
        except:
            content_height = 0
        self.toggle_button.setArrowType(Qt.ArrowType.DownArrow)
        self.content_area.setMaximumHeight(content_height)
        self.content_area.setMinimumHeight(content_height)

    def collapse(self):
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.content_area.setMaximumHeight(0)
        self.content_area.setMinimumHeight(0)

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
        self.setGeometry(100, 100, 500, 500)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        self.container_widget = QWidget()
        self.mainLayout = QVBoxLayout(self.container_widget)
        self.scroll_area.setWidget(self.container_widget)

        layout = QVBoxLayout(self)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

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

    def refresh_pm_data(self, machine_speed, selected_frequency):
        self.clearLayout(self.mainLayout)
        self.checkboxes.clear()
        self.group_checkboxes.clear()
        self.populate_pm_data(machine_speed)

        closest_element = None
        closest_frequency_diff = float('inf')
        closest_checkbox = None
        closest_label = None

        for group in self.pm_data:
            groupLayout = QHBoxLayout()
            groupCheckboxLayout = QVBoxLayout()
            groupName = group.get('groupName', 'Unnamed group')
            groupCheckbox = QCheckBox()
            groupBox = CollapsibleBox(groupName, collapsed=group.get('collapsed', COLLAPSE_BY_DEFAULT))
            self.group_checkboxes[groupCheckbox] = []
            groupBoxLayout = QVBoxLayout()

            groupCheckboxLayout.addWidget(groupCheckbox)
            groupCheckboxLayout.addStretch()

            groupLayout.addLayout(groupCheckboxLayout)
            groupLayout.addWidget(groupBox)
            self.mainLayout.addLayout(groupLayout)
            groupCheckbox.stateChanged.connect(lambda state, g=group, gc=groupCheckbox: self.onGroupCheckboxStateChanged(state, g, gc))
            groupBox.stateChanged.connect(lambda collapsed, group=group: self.onGroupBoxCollapseChanged(collapsed, group))

            if 'elements' in group and isinstance(group['elements'], list):
                for element in group['elements']:
                    # Add "indentation" to element checkboxes
                    elementCheckboxLayout = QHBoxLayout()
                    wavelength = 1 / element['spatial_frequency']

                    elementName = element.get('name', 'Unnamed Element')
                    if self.window_type == "MD":
                        checkbox = QCheckBox(f"{elementName}")
                        label = QLabel(f"{element['spatial_frequency']:.2f} 1/m {element['frequency_hz']:.2f} Hz (λ = {100*wavelength:.2f} cm)")
                    elif self.window_type == "CD":
                        checkbox = QCheckBox(f"{elementName}")
                        label = QLabel(f"{element['spatial_frequency']:.2f} 1/m (λ = {100*wavelength:.2f} cm)")

                    if selected_frequency:
                        # Check if this element is closest to the selected frequency
                        frequency_diff = abs(element['spatial_frequency'] - selected_frequency)
                        if frequency_diff < closest_frequency_diff:
                            closest_frequency_diff = frequency_diff
                            closest_checkbox = checkbox
                            closest_label = label
                            closest_groupbox = groupBox

                    checkbox.setChecked(element.get('checked', False))
                    checkbox.setProperty('element', element)
                    checkbox.stateChanged.connect(lambda state, elem=element, gc=groupCheckbox: self.onElementCheckboxStateChanged(state, elem, gc))

                    elementCheckboxLayout.addWidget(checkbox)
                    elementCheckboxLayout.addWidget(label)
                    label.setAlignment(Qt.AlignmentFlag.AlignRight)
                    groupBoxLayout.addLayout(elementCheckboxLayout)
                    self.checkboxes.append(checkbox)
                    self.group_checkboxes[groupCheckbox].append(checkbox)

            self.updateGroupCheckboxState(groupCheckbox)
            groupBox.setContentLayout(groupBoxLayout)

        self.mainLayout.addStretch(1)

        # Highlight the closest element
        if closest_checkbox and closest_label and closest_groupbox:
            closest_checkbox.setStyleSheet("background-color: lightskyblue;")  # Customize the highlight color
            closest_label.setStyleSheet("background-color: lightskyblue;")      # Same color for the label
            closest_groupbox.expand()


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

    def onGroupBoxCollapseChanged(self, collapsed, group):
        group['collapsed'] = collapsed
