from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QMessageBox
)
from PyQt6.QtGui import QIcon
import os
import settings
from datetime import datetime

class CrashDialog(QDialog):
    def __init__(self, log_manager, traceback_text, parent=None):
        super().__init__(parent)
        self.log_manager = log_manager
        self.traceback_text = traceback_text
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Tapio Analysis - Unexpected Error")
        self.setWindowIcon(QIcon(os.path.join(settings.ASSETS_DIR, "tapio_icon.ico")))
        self.setMinimumSize(700, 500)

        # Main layout
        layout = QVBoxLayout()

        # Error message
        error_label = QLabel(
            "<h3>An unexpected error has occurred</h3>"
            "<p>The application encountered a problem that it couldn't handle.<br>"
            "Please save the full error log using the button below and send it to "
            f"<a href='mailto:{settings.CRASH_DIALOG_CONTACT_EMAIL}'>{settings.CRASH_DIALOG_CONTACT_EMAIL}</a>.</p>"
        )
        error_label.setWordWrap(True)
        error_label.setOpenExternalLinks(True)
        layout.addWidget(error_label)

        # Traceback display
        self.traceback_edit = QTextEdit()
        self.traceback_edit.setReadOnly(True)
        self.traceback_edit.setPlainText(self.traceback_text)
        layout.addWidget(self.traceback_edit)

        # Buttons
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Save Error Log")
        self.save_button.clicked.connect(self.save_log)

        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)

        button_layout.addWidget(self.close_button)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def save_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"tapio_crash_{timestamp}.log"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Crash Log",
            default_name,
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            (success, msg) = self.log_manager.export_logs(file_path)
            if success:
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.critical(self, "Error", msg)
