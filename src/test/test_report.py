import unittest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication
import sys
from gui.report import ReportWindow

class TestReportWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a QApplication instance for testing
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        # Initialize the main window and report window
        self.main_window = MagicMock()
        self.report_window = ReportWindow(self.main_window)

    def tearDown(self):
        # Close the report window
        self.report_window.close()

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
        self.report_window.choose_image()
        self.assertEqual(self.report_window.header_image_path, "test_image.png")
        self.assertEqual(self.report_window.header_image_path_input.text(), "test_image.png")

    @patch('PyQt6.QtWidgets.QFileDialog.getSaveFileName')
    def test_generate_report(self, mock_getSaveFileName):
        # Mock the file dialog to simulate saving a DOCX file
        mock_getSaveFileName.return_value = ("test_report.docx", "")
        self.report_window.generate_report()
        # Verify the save file dialog was called
        mock_getSaveFileName.assert_called_once()
        # Check if the file name ends with '.docx'
        self.assertTrue(mock_getSaveFileName.return_value[0].endswith('.docx'))

    @patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data='{"report_title": "Test Report", "sections": {"MD": []}}')
    @patch('json.load')
    def test_load_from_json(self, mock_json_load, mock_open, mock_getOpenFileName):
        # Mock the file dialog to return a specific file path and load JSON data
        mock_getOpenFileName.return_value = ("test_data.json", "")
        mock_json_load.return_value = {"report_title": "Test Report", "sections": {"MD": []}}
        self.report_window.load_from_json()
        self.assertEqual(self.report_window.report_title, "Test Report")
        self.assertEqual(self.report_window.title_input.text(), "Test Report")

if __name__ == "__main__":
    unittest.main()
