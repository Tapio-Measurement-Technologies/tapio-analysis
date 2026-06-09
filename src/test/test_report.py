import unittest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
import sys
import os
import tempfile
from gui.report import ReportWindow
from utils.measurement import Measurement

class TestReportWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a QApplication instance for testing
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        # Initialize the main window and report window
        self.temp_dir = tempfile.TemporaryDirectory()
        self.main_window = MagicMock()
        self.measurement = Measurement(measurement_label="Test measurement")
        self.speed_patcher = patch(
            "PyQt6.QtWidgets.QInputDialog.getDouble",
            return_value=(1600.0, True),
        )
        self.speed_patcher.start()
        self.report_window = ReportWindow(self.main_window, self.measurement)

    def tearDown(self):
        # Close the report window
        self.report_window.close()
        self.speed_patcher.stop()
        self.temp_dir.cleanup()

    def test_initialization(self):
        # Test if the window and main layout are initialized correctly
        self.assertEqual(self.report_window.window_type, "MD")
        self.assertEqual(self.report_window.report_title, "MD Report")
        self.assertIsNotNone(self.report_window.main_layout)

    def test_add_section(self):
        # Test adding a section
        initial_count = len(self.report_window.section_widgets)
        self.report_window.add_section()
        self.assertEqual(len(self.report_window.section_widgets), initial_count + 1)

    def test_update_report_title(self):
        # Test updating the report title
        new_title = "New Report Title"
        self.report_window.update_report_title(new_title)
        self.assertEqual(self.report_window.report_title, new_title)
        self.assertEqual(self.report_window.title_input.text(), new_title)

    @patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName')
    def test_choose_image(self, mock_getOpenFileName):
        # Mock the file dialog to return a specific file path
        mock_getOpenFileName.return_value = ("test_image.png", "")
        self.report_window.choose_header_image()
        self.assertEqual(self.report_window.header_image_path, "test_image.png")
        self.assertEqual(self.report_window.header_image_path_input.text(), "test_image.png")

    @patch('PyQt6.QtWidgets.QMessageBox.information')
    @patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
    def test_generate_report(self, mock_getSaveFileName, mock_information):
        # Mock the file dialog to simulate saving a DOCX file
        output_path = os.path.join(self.temp_dir.name, "test_report.docx")
        mock_getSaveFileName.return_value = (output_path, "")
        self.report_window.generate_report()
        # Verify the save file dialog was called
        mock_getSaveFileName.assert_called_once()
        # Check if the file name ends with '.docx'
        self.assertTrue(mock_getSaveFileName.return_value[0].endswith('.docx'))
        self.assertTrue(os.path.exists(output_path))

    def test_load_from_python_template(self):
        template_path = os.path.join(self.temp_dir.name, "report_template.py")
        with open(template_path, "w", encoding="utf-8") as template:
            template.write(
                'report_title = "Test Report"\n'
                'report_subtitle = "Test Subtitle"\n'
                'sections = []\n'
            )

        self.report_window.load_from_python(template_path)

        self.assertEqual(self.report_window.report_title, "Test Report")
        self.assertEqual(self.report_window.title_input.text(), "Test Report")
        self.assertEqual(self.report_window.report_subtitle, "Test Subtitle")

if __name__ == "__main__":
    unittest.main()
