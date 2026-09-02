"""A machine speed of zero means the speed is not known.

Every spatial frequency the analyses report can also be quoted as a machine
frequency, but only once the reel speed is known. Multiplying by a speed of zero
gives 0.00 Hz for every frequency, which reads as a measurement rather than as a
blank, so the Hz reading is left out entirely instead.
"""

import numpy as np
import pytest

from gui.paper_machine_data import PaperMachineDataWindow
from utils.measurement import Measurement
from utils.plot_formatting import (frequency_in_hz, hz_suffix,
                                   machine_speed_is_known)


@pytest.mark.parametrize("speed", [0, 0.0, -1, None, "", "not a number"])
def test_machine_speed_is_not_known(speed):
    assert machine_speed_is_known(speed) is False


@pytest.mark.parametrize("speed", [1600, 1600.0, "1600", 0.1])
def test_machine_speed_is_known(speed):
    assert machine_speed_is_known(speed) is True


def test_frequency_in_hz_converts_with_a_speed():
    # 0.945 1/m at 1600 m/min is 0.945 * 1600 / 60 Hz.
    assert frequency_in_hz(0.945, 1600) == pytest.approx(25.2)


def test_frequency_in_hz_is_none_without_a_speed():
    assert frequency_in_hz(0.945, 0) is None


def test_hz_suffix_is_empty_without_a_speed():
    assert hz_suffix(0.945, 1600) == " (25.20 Hz)"
    assert hz_suffix(0.945, 0) == ""


def _pm_window(qt_app, elements):
    measurement = Measurement()
    measurement.pm_data = {
        "MD": [{"groupName": "Test group", "elements": elements}]}
    return PaperMachineDataWindow(
        lambda *args: None, "MD", [], measurement)


def test_pm_elements_given_by_length_survive_a_zero_speed(qt_app):
    """A length or a diameter fixes a spacing without needing a speed."""
    window = _pm_window(qt_app, [{"name": "Roll", "length": 0.5}])

    window.populate_pm_data(0)
    element = window.pm_data[0]["elements"][0]

    assert element["spatial_frequency"] == pytest.approx(2.0)
    assert element["frequency_hz"] is None


def test_pm_elements_given_in_hz_are_dropped_at_a_zero_speed(qt_app):
    """Without a speed there is no distance a running frequency maps onto."""
    window = _pm_window(qt_app, [{"name": "Fan pump", "frequency": 24.0}])

    # The division that used to raise ZeroDivisionError.
    window.populate_pm_data(0)
    element = window.pm_data[0]["elements"][0]

    assert element["spatial_frequency"] is None
    assert element["frequency_hz"] is None


def test_pm_elements_given_in_hz_resolve_with_a_speed(qt_app):
    window = _pm_window(qt_app, [{"name": "Fan pump", "frequency": 24.0}])

    window.populate_pm_data(1600)
    element = window.pm_data[0]["elements"][0]

    # 24 Hz at 1600 m/min repeats every 1600/60/24 m.
    assert element["spatial_frequency"] == pytest.approx(24.0 / (1600 / 60))
    assert element["frequency_hz"] == pytest.approx(24.0)


def test_pm_window_renders_with_a_zero_speed(qt_app):
    """The window must still build, listing only the placeable elements."""
    window = _pm_window(qt_app, [
        {"name": "Roll", "length": 0.5},
        {"name": "Fan pump", "frequency": 24.0},
    ])

    window.refresh_pm_data(0, None)

    labels = [box.text() for box in window.checkboxes]
    assert labels == ["Roll"]
    assert not any("Hz" in box.text() for box in window.checkboxes)
