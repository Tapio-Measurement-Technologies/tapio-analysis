# Tapio Analysis
# Copyright 2024 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

from utils.log_stream import EmittingStream, EmittingStreamType

# Replaces sys.stdout and sys.stderr
stdout_stream = EmittingStream(EmittingStreamType.STDOUT)
stderr_stream = EmittingStream(EmittingStreamType.STDERR)

from utils.logging import LogManager
import settings
from utils import store

# Create log manager and store it in the global store
store.log_manager = LogManager(stdout_stream, stderr_stream, settings.LOG_WINDOW_MAX_LINES, settings.LOG_WINDOW_SHOW_TIMESTAMPS)


from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtGui import QIcon
import logging
import os
import sys
import traceback

from gui.main_window import MainWindow

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to exit as usual
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Format traceback
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    store.log_manager.handle_crash(tb)

# Set global exception handler
sys.excepthook = handle_exception

def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(
        QIcon(os.path.join(settings.ASSETS_DIR, "tapio_icon.ico")))

    app.setStyle(QStyleFactory.create('Fusion'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

# Show splash screen on standalone pyinstaller executable
try:
    import pyi_splash
    pyi_splash.update_text("Loading Tapio Analysis...")
    pyi_splash.close()
except:
    print('Skipping splash screen...')
    pass

if __name__ == '__main__':
    # main_debug()
    main()
