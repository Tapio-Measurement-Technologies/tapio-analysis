import time
import platform
from datetime import datetime
import sys
import settings
from collections import deque
from PyQt6.QtCore import QObject, pyqtSignal
from utils.log_stream import EmittingStream

# TODO: This whole module could be refactored to use python's logging module which does most of these things already

launch_time = time.time()

def get_platform_info_header():
    uptime_sec = int(time.time() - launch_time)
    uptime_str = f"{uptime_sec // 60}m {uptime_sec % 60}s"
    cli_args = " ".join(sys.argv)

    # Include all UPPERCASE variables from settings
    from inspect import ismodule
    setting_lines = [
        f"{key:30}: {getattr(settings, key)}"
        for key in dir(settings)
        if key.isupper() and not key.startswith("_") and not ismodule(getattr(settings, key))
    ]

    header = [
        "==== Platform Info ====",
        f"Exported at               : {datetime.now().isoformat()}",
        f"OS                        : {platform.system()} {platform.release()}",
        f"Python Version            : {platform.python_version()}",
        f"Uptime                    : {uptime_str}",
        f"Command-line Arguments    : {cli_args}\n",
        "--- Settings ---"
    ] + setting_lines + ["========================"]

    return "\n".join(header)


class LogManager(QObject):
    log_updated = pyqtSignal()

    def __init__(self, stdout_stream: EmittingStream, stderr_stream: EmittingStream, max_lines=1000, show_timestamps=True):
        super().__init__()
        self.max_lines = max_lines
        self.show_timestamps = show_timestamps
        self.log_buffer = deque(maxlen=max_lines)
        self.log_lines_raw = deque(maxlen=max_lines)
        self.active_levels = {"INFO", "ERROR"}

        # Initialize streams
        self.stdout_stream = stdout_stream
        self.stderr_stream = stderr_stream

        # Connect streams to log handlers
        self.stdout_stream.textWritten.connect(lambda msg: self.append_message(msg, "INFO"))
        self.stderr_stream.textWritten.connect(lambda msg: self.append_message(msg, "ERROR"))

    def append_message(self, message, level="INFO"):
        from PyQt6.QtCore import QTime

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

        self.log_updated.emit()

    def get_filtered_logs(self, active_levels=None):
        levels = active_levels if active_levels is not None else self.active_levels
        return [
            html for level, html in self.log_buffer
            if level in levels
        ]

    def clear_logs(self):
        self.log_buffer.clear()
        self.log_lines_raw.clear()
        self.log_updated.emit()

    def get_raw_logs(self):
        return list(self.log_lines_raw)

    def export_logs(self, file_path):
        """Export logs to a file with platform information header"""
        try:
            platform_info = get_platform_info_header()
            raw_logs = self.get_raw_logs()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(platform_info + "\n" + "\n".join(raw_logs))
            print(f"Log exported to {file_path}")
            return True
        except Exception as e:
            print(f"Error saving log: {e}")
            return False

    def _escape_html(self, text):
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )