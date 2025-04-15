from PyQt6.QtWidgets import (
    QTextEdit, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QFileDialog, QLabel
)
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QMessageBox
from utils.logging import LogManager
from datetime import datetime

class LogWindow(QWidget):
    def __init__(self, log_manager: LogManager):
        super().__init__()
        self.setWindowTitle("Application logs")
        self.setMinimumSize(800, 400)

        # Use provided log manager or create a new one
        self.log_manager = log_manager
        self.log_manager.log_updated.connect(self.refresh_text_edit)

        # Layouts
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

        self.init_filters()
        self.init_buttons()

        main_layout = QVBoxLayout()
        main_layout.addLayout(self.filter_layout)
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(self.button_layout)
        self.setLayout(main_layout)

        self.refresh_text_edit()

    def init_filters(self):
        self.filter_layout = QHBoxLayout()
        self.filter_label = QLabel("Filters:")
        self.check_info = QCheckBox("INFO")
        self.check_error = QCheckBox("ERROR")

        self.filter_layout.addWidget(self.filter_label)
        for checkbox in [self.check_info, self.check_error]:
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.update_active_levels)
            self.filter_layout.addWidget(checkbox)

        self.filter_layout.addStretch()

    def init_buttons(self):
        self.clear_button = QPushButton("Clear logs")
        self.export_button = QPushButton("Export to file")

        self.clear_button.setMinimumWidth(200)
        self.export_button.setMinimumWidth(200)

        self.clear_button.clicked.connect(self.clear_log)
        self.export_button.clicked.connect(self.export_log)

        self.button_layout = QHBoxLayout()
        self.button_layout.addWidget(self.clear_button)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.export_button)

    def update_active_levels(self):
        active_levels = set()
        if self.check_info.isChecked():
            active_levels.add("INFO")
        if self.check_error.isChecked():
            active_levels.add("ERROR")
        self.log_manager.active_levels = active_levels
        self.refresh_text_edit()

    def refresh_text_edit(self):
        filtered_logs = self.log_manager.get_filtered_logs()
        self.text_edit.setHtml("<br>".join(filtered_logs))
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.log_manager.clear_logs()
        self.text_edit.clear()

    def export_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"log_{timestamp}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", default_name, "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )
        if path:
            (success, msg) = self.log_manager.export_logs(path)
            if success:
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.critical(self, "Error", msg)
