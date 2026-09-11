"""A small aid for setting the band pass filter in the units at hand.

The band pass slider works in 1/m, while the question usually comes as a
wavelength -- keep everything longer than 10 m -- or as a machine frequency in
Hz, and converting by hand is where a decimal goes astray. The aid takes the
two limits of the band in a unit of choice and hands the slider the band.
"""

from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                             QLabel, QLineEdit, QVBoxLayout)

from utils.plot_formatting import machine_speed_is_known

#: Metres per unit.
WAVELENGTH_UNITS = {"Wavelength [mm]": 0.001, "Wavelength [cm]": 0.01, "Wavelength [m]": 1.0}
FREQUENCY_UNIT = "Frequency [1/m]"
HZ_UNIT = "Frequency [Hz]"
UNITS = [*WAVELENGTH_UNITS, FREQUENCY_UNIT, HZ_UNIT]


def parse_limit(text):
    """A typed limit as a number above zero, or None when the field is blank."""
    text = str(text).strip().replace(",", ".")
    if not text:
        return None
    value = float(text)
    if not value > 0:
        raise ValueError("a limit must be above zero")
    return value


def to_frequency_1m(value, unit, machine_speed=None):
    """A limit typed in ``unit`` as a spatial frequency in 1/m."""
    if unit in WAVELENGTH_UNITS:
        return 1.0 / (value * WAVELENGTH_UNITS[unit])
    if unit == HZ_UNIT:
        if not machine_speed_is_known(machine_speed):
            raise ValueError("Hz needs the machine speed")
        return value * 60.0 / float(machine_speed)
    return float(value)


def from_frequency_1m(frequency, unit, machine_speed=None):
    """A spatial frequency in 1/m written in ``unit``: to_frequency_1m reversed."""
    if unit in WAVELENGTH_UNITS:
        return 1.0 / (frequency * WAVELENGTH_UNITS[unit])
    if unit == HZ_UNIT:
        return frequency * float(machine_speed) / 60.0
    return float(frequency)


def limit_labels(unit):
    """What the two limits are called in ``unit``."""
    if unit in WAVELENGTH_UNITS:
        return "Longest wavelength kept", "Shortest wavelength kept"
    return "Low cut", "High cut"


def band_from_limits(first, second, unit, maximum, machine_speed=None):
    """The band ``(low, high)`` in 1/m that the two typed limits describe.

    In a frequency unit the limits are the low and the high cut. In a
    wavelength unit they are the longest and the shortest wavelength kept,
    which turn into the low and the high cut. A blank limit leaves its end of
    the band open: the low cut at zero, the high cut at ``maximum``, the
    highest the filter allows. Neither cut goes past ``maximum``, and two
    limits in the wrong order are taken in the right one.
    """
    cuts = []
    for text in (first, second):
        value = parse_limit(text)
        cuts.append(None if value is None else to_frequency_1m(value, unit, machine_speed))
    low = 0.0 if cuts[0] is None else min(cuts[0], maximum)
    high = maximum if cuts[1] is None else min(cuts[1], maximum)
    low, high = min(low, high), max(low, high)
    if not low < high:
        raise ValueError("the band is empty")
    return low, high


def wavelength_text(frequency):
    """The wavelength of a frequency in 1/m, in metres or centimetres."""
    metres = 1.0 / frequency
    if metres >= 100:
        return f"{metres:.0f} m"
    if metres >= 1:
        return f"{metres:.3g} m"
    return f"{100 * metres:.3g} cm"


def band_text(low, high):
    """``Band pass 0.100 - 10.000 1/m, wavelengths 10 cm - 10 m``."""
    longest = "∞" if low <= 0 else wavelength_text(low)
    return f"Band pass {low:.3f} - {high:.3f} 1/m, wavelengths {wavelength_text(high)} - {longest}"


class FilterAidDialog(QDialog):
    """Two limits in a unit of choice, and the band they make."""

    def __init__(self, parent, band, maximum, machine_speed=None, unit="Wavelength [cm]"):
        super().__init__(parent)
        self.setWindowTitle("Filter aid")
        self.maximum = float(maximum)
        self.machine_speed = machine_speed
        self.band = tuple(float(value) for value in band)

        self.unitSelector = QComboBox()
        self.unitSelector.addItems(UNITS)
        if not machine_speed_is_known(machine_speed):
            item = self.unitSelector.model().item(UNITS.index(HZ_UNIT))
            item.setEnabled(False)
            item.setToolTip("Set the machine speed to give the band in Hz")
        self.firstLabel, self.secondLabel = QLabel(), QLabel()
        self.firstEdit, self.secondEdit = QLineEdit(), QLineEdit()
        self.firstEdit.setPlaceholderText("open")
        self.secondEdit.setPlaceholderText("open")
        self.resultLabel = QLabel()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

        grid = QGridLayout()
        grid.addWidget(QLabel("Unit"), 0, 0)
        grid.addWidget(self.unitSelector, 0, 1)
        grid.addWidget(self.firstLabel, 1, 0)
        grid.addWidget(self.firstEdit, 1, 1)
        grid.addWidget(self.secondLabel, 2, 0)
        grid.addWidget(self.secondEdit, 2, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self.resultLabel)
        layout.addWidget(self.buttons)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.unitSelector.setCurrentText(unit)
        self.unitSelector.currentTextChanged.connect(self.unitChanged)
        self.firstEdit.textEdited.connect(self.updateResult)
        self.secondEdit.textEdited.connect(self.updateResult)
        self.unitChanged(self.unitSelector.currentText())

    def unitChanged(self, unit):
        """Relabel the limits and write the band so far in the new unit."""
        first, second = limit_labels(unit)
        self.firstLabel.setText(first)
        self.secondLabel.setText(second)
        low, high = self.band
        self.firstEdit.setText(self._written(low, unit) if low > 0 else "")
        self.secondEdit.setText(self._written(high, unit) if high < self.maximum else "")
        self.updateResult()

    def _written(self, frequency, unit):
        return f"{from_frequency_1m(frequency, unit, self.machine_speed):.4g}"

    def updateResult(self, *_):
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        try:
            self.band = band_from_limits(
                self.firstEdit.text(), self.secondEdit.text(),
                self.unitSelector.currentText(), self.maximum, self.machine_speed)
        except ValueError as error:
            self.resultLabel.setText(f"Not a band: {error}")
            ok_button.setEnabled(False)
            return
        self.resultLabel.setText(band_text(*self.band))
        ok_button.setEnabled(True)
