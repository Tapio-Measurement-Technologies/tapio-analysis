import sys
import os
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
from main import MainWindow
from utils.data_loader import DataMixin


class TestMainApp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication(sys.argv)
        cls.main_window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls.main_window.close()
        cls.app.quit()

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

        # Load files using DataMixin
        self._load_files(test_data_folder, test_files)

        # Trigger the refresh to update the UI based on loaded data
        self.main_window.refresh()

        # Check if windows open successfully
        self._open_window(self.main_window.findSamplesButton, self.main_window.openFindSamples)
        self._open_window(self.main_window.MDReportButton, lambda: self.main_window.openReport(window_type="MD"))
        self._open_window(self.main_window.CDReportButton, lambda: self.main_window.openReport(window_type="CD"))

        for analysis in self.main_window.md_analyses.values():
            self._open_window(analysis["button"], analysis["callback"])

        for analysis in self.main_window.cd_analyses.values():
            self._open_window(analysis["button"], analysis["callback"])

    def _load_files(self, folder_path, files):
        data_mixin = DataMixin.getInstance()

        header_file = os.path.join(folder_path, files['header'])
        calibration_file = os.path.join(folder_path, files['calibration'])
        data_file = os.path.join(folder_path, files['data'])
        pm_file = os.path.join(folder_path, files['pm'])
        samples_file = os.path.join(folder_path, files['samples'])

        # Load legacy data
        data_mixin.header_file_path = header_file
        data_mixin.calibration_file_path = calibration_file
        data_mixin.data_file_path = data_file
        data_mixin.load_legacy_data()

        # Load paper machine data
        data_mixin.pm_file_path = pm_file
        data_mixin.load_pm_file()

        # Load sample locations
        data_mixin.samples_file_path = samples_file
        data_mixin.load_cd_samples_data()

    def _open_window(self, button, callback):
        # Ensure the button is enabled
        self.assertTrue(button.isEnabled(), f"{button.text()} button should be enabled")

        # Click the button to open the window
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        callback()

        # Allow the window to process events
        self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
