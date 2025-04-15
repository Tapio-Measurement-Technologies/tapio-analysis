from PyQt6.QtWidgets import (
    QTextEdit, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QFileDialog
)
from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import QTime
from utils.log_stream import EmittingStream
from utils.logging import get_platform_info_header
from collections import deque
from datetime import datetime
import time

class LogWindow(QWidget):
    def __init__(self, stdout_stream: EmittingStream, stderr_stream: EmittingStream, max_lines=1000, show_timestamps=True):
        super().__init__()
        self.setWindowTitle("Application logs")
        self.setMinimumSize(800, 400)

        # Settings
        self.max_lines = max_lines
        self.show_timestamps = show_timestamps
        self.log_buffer = deque(maxlen=max_lines)
        self.log_lines_raw = deque(maxlen=max_lines)
        self.active_levels = {"INFO", "ERROR"}
        self.launch_time = time.time()

        # Streams
        self.stdout_stream = stdout_stream
        self.stderr_stream = stderr_stream
        self.stdout_stream.textWritten.connect(lambda msg: self.append_message(msg, "INFO"))
        self.stderr_stream.textWritten.connect(lambda msg: self.append_message(msg, "ERROR"))

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

    def init_filters(self):
        self.filter_layout = QHBoxLayout()
        self.check_info = QCheckBox("INFO")
        self.check_error = QCheckBox("ERROR")

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
        self.active_levels.clear()
        if self.check_info.isChecked():
            self.active_levels.add("INFO")
        if self.check_error.isChecked():
            self.active_levels.add("ERROR")
        self.refresh_text_edit()

    def append_message(self, message, level="INFO"):
        color_map = {
            "INFO": "black",
            "ERROR": "red"
        }

        lines = message.rstrip().splitlines()
        if not lines:
            return

        for line in lines:
            timestamp = QTime.currentTime().toString("HH:mm:ss.zzz") if self.show_timestamps else ""
            color = color_map.get(level, "black")
            level_tag = f"[{level}]"

            # HTML log version
            html_line = (
                f'<span style="color:gray">[{timestamp}]</span> '
                f'<span style="color:{color}">{level_tag} {self._escape_html(line)}</span>'
            )

            # Raw log version (for export)
            plain_line = f"[{timestamp}] {level_tag} {line}"

            self.log_buffer.append((level, html_line))
            self.log_lines_raw.append(plain_line)

        self.refresh_text_edit()

    def refresh_text_edit(self):
        filtered = [
            html for level, html in self.log_buffer
            if level in self.active_levels
        ]
        self.text_edit.setHtml("<br>".join(filtered))
        self.text_edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear_log(self):
        self.log_buffer.clear()
        self.log_lines_raw.clear()
        self.text_edit.clear()

    def export_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"log_{timestamp}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Log", default_name, "Log Files (*.log);;Text Files (*.txt);;All Files (*)"
        )
        if path:
            try:
                platform_info = get_platform_info_header()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(platform_info + "\n" + "\n".join(self.log_lines_raw))
                print(f"Log exported to {path}")
            except Exception as e:
                print(f"Error saving log: {e}")

    def _escape_html(self, text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )