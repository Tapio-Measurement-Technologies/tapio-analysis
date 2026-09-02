"""Toolbar navigation on the analysis plots: zooming, and what home restores."""

import warnings

import numpy as np
import pandas as pd
import pytest
from matplotlib.backend_bases import MouseButton, MouseEvent

from analyses import find_samples, spectrum
from utils.measurement import Measurement

SAMPLE_STEP = 0.01
FUNDAMENTAL = 5.0


def make_md_measurement():
    distances = np.arange(8192, dtype=float) * SAMPLE_STEP
    signal = np.sin(2 * np.pi * FUNDAMENTAL * distances)
    return Measurement(
        channel_df=pd.DataFrame({"A": signal}),
        channels=["A"],
        units={"A": "u"},
        distances=distances,
        cd_distances=distances,
        sample_step=SAMPLE_STEP,
    )


def make_spectrum_window():
    controller = spectrum.AnalysisController(make_md_measurement(), "MD")
    return spectrum.AnalysisWindow(controller, "MD")


def make_find_samples_window():
    controller = find_samples.AnalysisController(make_md_measurement(), "MD")
    return find_samples.AnalysisWindow(controller, "MD")


def zoom_to(window, x_low, x_high, keep_active=False):
    """Zoom the plot to a frequency range the way the toolbar's zoom tool does."""
    controller = window.controller
    canvas = controller.canvas
    toolbar = controller.toolbar
    ax = controller.figure.axes[0]
    y_low, y_high = ax.get_ylim()

    press = ax.transData.transform((x_low, y_low + 0.05 * (y_high - y_low)))
    release = ax.transData.transform((x_high, y_low + 0.95 * (y_high - y_low)))

    toolbar.zoom()
    toolbar.press_zoom(MouseEvent(
        'button_press_event', canvas, press[0], press[1], MouseButton.LEFT))
    toolbar.release_zoom(MouseEvent(
        'button_release_event', canvas, release[0], release[1], MouseButton.LEFT))
    if not keep_active:
        toolbar.zoom()


def test_spectrum_middle_click_works_while_zoom_tool_stays_active(qt_app):
    window = make_spectrum_window()
    controller = window.controller

    zoom_to(window, FUNDAMENTAL - 1, FUNDAMENTAL + 1, keep_active=True)
    zoomed_view = controller.figure.axes[0].get_xlim()
    assert controller.toolbar.mode

    ax = controller.figure.axes[0]
    target_frequency = FUNDAMENTAL + 0.25
    click = ax.transData.transform((target_frequency, np.mean(ax.get_ylim())))
    controller.canvas.callbacks.process('button_press_event', MouseEvent(
        'button_press_event', controller.canvas, click[0], click[1],
        MouseButton.MIDDLE,
    ))

    assert controller.selected_freqs[-1] == pytest.approx(
        controller.snap_frequency_to_bin(target_frequency)
    )
    assert controller.figure.axes[0].get_xlim() == pytest.approx(zoomed_view)


def test_find_samples_middle_click_works_while_zoom_tool_stays_active(qt_app):
    window = make_find_samples_window()
    controller = window.controller

    zoom_to(window, 1.0, 2.0, keep_active=True)
    ax = controller.figure.axes[0]
    zoomed_xlim = ax.get_xlim()
    zoomed_ylim = ax.get_ylim()
    threshold = np.mean(zoomed_ylim)
    click = ax.transData.transform((1.5, threshold))

    controller.canvas.callbacks.process('button_press_event', MouseEvent(
        'button_press_event', controller.canvas, click[0], click[1],
        MouseButton.MIDDLE,
    ))

    assert controller.threshold == pytest.approx(threshold)
    assert controller.figure.axes[0].get_xlim() == pytest.approx(zoomed_xlim)
    assert controller.figure.axes[0].get_ylim() == pytest.approx(zoomed_ylim)


def test_home_returns_to_the_parameter_view_after_a_restored_zoom(qt_app):
    """A refresh that keeps the zoom must not become what home restores.

    Selecting a frequency redraws the plot and puts the zoom back afterwards.
    The redraw clears the figure, which empties the toolbar's view stack, so
    without the plot pushing its own view the zoom is all home has left to go
    back to.
    """
    window = make_spectrum_window()
    controller = window.controller
    parameter_view = controller.figure.axes[0].get_xlim()

    zoom_to(window, FUNDAMENTAL - 1, FUNDAMENTAL + 1)
    zoomed_view = controller.figure.axes[0].get_xlim()
    assert zoomed_view[1] - zoomed_view[0] < parameter_view[1] - parameter_view[0]

    window.refresh(restore_lim=True)
    assert controller.figure.axes[0].get_xlim() == pytest.approx(zoomed_view)

    controller.toolbar.home()
    assert controller.figure.axes[0].get_xlim() == pytest.approx(parameter_view)


def test_home_returns_to_the_parameter_view_after_a_parameter_change(qt_app):
    window = make_spectrum_window()
    controller = window.controller

    zoom_to(window, FUNDAMENTAL - 1, FUNDAMENTAL + 1)
    controller.frequency_range_high = FUNDAMENTAL * 2
    window.refresh()
    parameter_view = controller.figure.axes[0].get_xlim()

    zoom_to(window, FUNDAMENTAL - 0.5, FUNDAMENTAL + 0.5)
    controller.toolbar.home()

    assert controller.figure.axes[0].get_xlim() == pytest.approx(parameter_view)


def test_harmonic_numbers_stay_inside_the_axes_when_zoomed(qt_app):
    """Zooming past a harmonic must not leave its number drawn in the margins.

    The numbers are text in data coordinates, which matplotlib does not clip by
    default. An unclipped one sitting far outside the view stretches the axes
    bounding box across the figure, and the constrained layout then gives up on
    the whole plot.
    """
    window = make_spectrum_window()
    controller = window.controller
    figure = controller.figure

    window.select_frequency_at(figure.axes[0], FUNDAMENTAL)
    zoom_to(window, FUNDAMENTAL - 1, FUNDAMENTAL + 1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        controller.canvas.draw()

    ax = figure.axes[0]
    assert [text.get_text() for text in ax.texts]  # Harmonics are numbered
    assert ax.get_tightbbox(controller.canvas.get_renderer()).width <= figure.bbox.width
    assert not [w for w in caught if "constrained_layout" in str(w.message)]
