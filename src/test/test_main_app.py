import sys
import os
import unittest
from superqt import QLabeledDoubleRangeSlider, QLabeledSlider
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication, QCheckBox, QMessageBox
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
from main import MainWindow
from analyses.cd_profile import AnalysisWindow as CDProfileWindow
from analyses.channel_correlation import AnalysisWindow as ChannelCorrelationWindow
from analyses.formation import AnalysisWindow as FormationWindow
from analyses.spectrogram import AnalysisWindow as SpectrogramWindow
from analyses.spectrum import AnalysisWindow as SpectrumWindow
from analyses.time_domain import AnalysisWindow as TimeDomainWindow
from analyses.vca import AnalysisWindow as VCAWindow
from loaders import tapio
from utils import store
import settings


class TestMainApp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.speed_patcher = patch(
            "PyQt6.QtWidgets.QInputDialog.getDouble",
            return_value=(1600.0, True),
        )
        cls.question_patcher = patch(
            "PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        )
        cls.speed_patcher.start()
        cls.question_patcher.start()
        cls.main_window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.main_window.closeAll()
        cls.main_window.close()
        cls.app.quit()
        cls.speed_patcher.stop()
        cls.question_patcher.stop()

    def test_load_files_and_open_windows(self):
        # Set the test data folder path
        test_data_folder = os.path.join(os.path.dirname(__file__), '../../test-data')

        # Files to load
        test_files = {
            'header': 'test_MD_L_1.pk2',
            'calibration': 'test_MD_L_1.ca2',
            'data': 'test_MD_L_1.da2',
            'pm': 'example_pm_data.pmdata.json',
            'samples': 'test_CD_samples.samples.json'
        }

        # Load files using current Tapio loader path
        self._load_files(test_data_folder, test_files)

        # Trigger the refresh to update the UI based on loaded data
        self.main_window.refresh()

        for module in self._configured_modules():
            if module.type == "CD" and not store.loaded_measurement.segments:
                self.assertFalse(module.button.isEnabled())
                continue

            self._open_and_interact_with_window(module.button)

    def _configured_modules(self):
        return [
            module
            for section in settings.ANALYSIS_SECTIONS
            for module in section.modules
        ]

    def _load_files(self, folder_path, files):
        header_file = os.path.join(folder_path, files['header'])
        calibration_file = os.path.join(folder_path, files['calibration'])
        data_file = os.path.join(folder_path, files['data'])
        pm_file = os.path.join(folder_path, files['pm'])
        samples_file = os.path.join(folder_path, files['samples'])

        measurement = tapio.load_data([
            header_file,
            calibration_file,
            data_file,
            pm_file,
            samples_file,
        ])

        self.assertIsNotNone(measurement)
        store.loaded_measurement = measurement

    def _open_and_interact_with_window(self, button):
        # Ensure the button is enabled
        self.assertTrue(button.isEnabled(), f"{button.text()} button should be enabled")

        # Click the button to open the window
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)

        # Allow the window to process events
        self.app.processEvents()

        # Interact with the window widgets
        self._interact_with_window()

    def _interact_with_window(self):
        # Perform interactions with the window widgets
        for window in store.open_windows:
            if isinstance(window, (CDProfileWindow, ChannelCorrelationWindow, FormationWindow, SpectrogramWindow, SpectrumWindow, TimeDomainWindow, VCAWindow)):
                self._toggle_checkboxes(window)
                self._move_sliders(window)

    def _toggle_checkboxes(self, window):
        # Find all checkboxes in the window and toggle them
        checkboxes = window.findChildren(QCheckBox)
        for checkbox in checkboxes:
            QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
            QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)

    def _move_sliders(self, window):
        # Find all sliders in the window and move them
        sliders = window.findChildren(QLabeledSlider)
        for slider in sliders:
            slider.setValue(slider.maximum())
            self.app.processEvents()
            slider.setValue(slider.minimum())
            self.app.processEvents()
        double_sliders = window.findChildren(QLabeledDoubleRangeSlider)
        for slider in double_sliders:
            slider.setValue((slider.minimum(), slider.maximum()))
            self.app.processEvents()
            slider.setValue((slider.minimum(), slider.minimum()))
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
