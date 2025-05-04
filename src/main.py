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
log_manager = LogManager(stdout_stream, stderr_stream, settings.LOG_WINDOW_MAX_LINES, settings.LOG_WINDOW_SHOW_TIMESTAMPS)

from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QMessageBox,
                             QMainWindow, QFileDialog, QFrame, QStyleFactory)
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtCore import Qt
import importlib

from gui.find_samples import FindSamplesWindow
from gui.report import ReportWindow
from utils.data_loader import DataMixin
from utils.windows import *
from utils.dynamic_loader import load_modules_from_folder
from utils.types import MeasurementFileType

import logging
import os
import sys
import traceback

from PyQt6.QtWidgets import QInputDialog

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class MainWindow(QMainWindow, DataMixin):

    def __init__(self):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.windows = []
        self.findSamplesWindow = None
        self.logWindow = None

        base_path = os.path.dirname(os.path.abspath(__file__))
        self.loaders = load_modules_from_folder(
            os.path.join(base_path, 'loaders'))
        self.exporters = load_modules_from_folder(
            os.path.join(base_path, 'exporters'))

        self.md_export_actions = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Tapio Analysis')
        # self.setGeometry(200, 200, 800, 600)  # x, y, width, height
        self.resize(800, 600)  # x, y, width, height

        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_center = screen_geometry.center()

        # Center the main window on the primary screen
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(screen_center)
        self.move(frame_geometry.topLeft())

        # Menu
        mainMenu = self.menuBar()
        fileMenu = mainMenu.addMenu('File')

        # Create menu items for each loaded module
        # Todo: Before adding the actions order these by menu_priority which is available from
        # action_priority = getattr(module, 'menu_priority', module_name)

        modules_sorted = sorted(
            self.loaders.items(),
            key=lambda item: getattr(item[1], 'menu_priority', 1)
        )

        first = True
        for module_name, module in modules_sorted:
            action_text = getattr(module, 'menu_text', module_name)
            action = QAction(action_text, self)

            # Set the action to load files for the specific module
            action.triggered.connect(
                lambda checked, mod=module: self.loadFiles(mod))
            fileMenu.addAction(action)

            # Assign shortcut to the first action only
            if first:
                action.setShortcut('Ctrl+O')
                first = False

        # Create menu items for export module
        for module_name, module in self.exporters.items():
            action_text = getattr(module, 'menu_text', module_name)
            action = QAction(action_text, self)
            action.triggered.connect(
                lambda checked, module=module: self.exportData(module))
            fileMenu.addAction(action)

            if len(self.exporters.items()) == 1:
                action.setShortcut('Ctrl+E')

            if module_name.startswith('md'):
                self.md_export_actions.append(action)

        self.closeAction = QAction('Close open files', self)
        self.closeAction.triggered.connect(self.closeAll)
        self.closeAction.setStatusTip("Close all open files")
        fileMenu.addAction(self.closeAction)

        # VIEW MENU
        viewMenu = mainMenu.addMenu('View')
        logWindowAction = QAction('Application logs', self)
        logWindowAction.triggered.connect(self.on_log_window_open)
        viewMenu.addAction(logWindowAction)

        # SETTINGS MENU
        settings_menu = mainMenu.addMenu('Settings')

        # reload_settings_action = QAction("Reload Settings", self)
        # reload_settings_action.triggered.connect(self.reload_settings)
        # settings_menu.addAction(reload_settings_action)
        set_settings_action = QAction("Set Settings", self)
        set_settings_action.triggered.connect(self.set_settings)
        settings_menu.addAction(set_settings_action)

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        layout = QVBoxLayout(centralWidget)
        # Ensure everything is aligned to the top
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Load and display logo

        logoLayout = QHBoxLayout()  # Create a new QHBoxLayout for logo and file pickers
        self.logoLabel = QLabel(self)
        pixmap = QPixmap(os.path.join(
            settings.ASSETS_DIR, 'Tapio_Logo_300dpi.png'))
        scaledPixmap = pixmap.scaled(
            200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        self.logoLabel.setPixmap(scaledPixmap)
        logoLayout.addWidget(self.logoLabel)

        # File Pickers

        self.fileLabels = {}
        for fileType in MeasurementFileType:
            self.addFilePicker(logoLayout, fileType)

        # Add the logo and file pickers layout to the main layout
        layout.addLayout(logoLayout)

        # Analysis Buttons
        self.setupAnalysisButtons(layout)
        self.refresh()

    def set_settings(self):
        # Step 1: Ask user for the setting key
        setting_key, ok = QInputDialog.getText(
            self, "Enter Setting Name", "Setting Key:")

        if not ok or not setting_key:
            return  # User canceled the input

        # Step 2: Check if the key exists in settings
        if not hasattr(settings, setting_key):
            QMessageBox.warning(self, "Error", f"Setting '{
                                setting_key}' does not exist.")
            return

        # Step 3: Get the current value and determine its type
        current_value = getattr(settings, setting_key)
        value_type = type(current_value)

        # Step 4: Ask for a new value
        new_value, ok = QInputDialog.getText(self, "Enter New Value", f"Current ({
                                             value_type.__name__}): {current_value}\nNew Value:")

        if not ok or not new_value:
            return  # User canceled input

        # Step 5: Convert the input to the correct type
        try:
            if value_type == int:
                new_value = int(new_value)
            elif value_type == float:
                new_value = float(new_value)
            elif value_type == bool:
                new_value = new_value.lower() in ['true', '1', 'yes']
            elif value_type == list:
                # Assuming comma-separated values
                new_value = new_value.split(",")
            else:
                new_value = str(new_value)  # Default to string

            # Step 6: Update settings
            setattr(settings, setting_key, new_value)
            QMessageBox.information(self, "Success", f"Setting '{
                                    setting_key}' updated to {new_value}.")

        except ValueError:
            QMessageBox.warning(
                self, "Error", "Invalid input type. Please enter a valid value.")

    def reload_settings(self):
        if "settings" in sys.modules:
            del sys.modules["settings"]
        import settings
        importlib.reload(settings)  # Reload the settings module
        print("Settings reloaded:", settings.__dict__)  # Debugging output
        print("Reloaded settings")

    def loadFiles(self, loader_module):
        file_types = getattr(loader_module, 'file_types', "All Files (*)")
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileNames, _ = QFileDialog.getOpenFileNames(
            self,
            "Open File",
            "",
            file_types,
            options=options)

        if fileNames:
            if len(self.windows) > 0:
                response = QMessageBox.question(self, 'Confirm open new file',
                                                'This will close all current analysis windows. Do you want to proceed?',
                                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if response == QMessageBox.StandardButton.No:
                    return

            self.closeAll()
            try:
                loader_module.load_data(fileNames)
            except Exception as e:
                self.dataMixin.reset()
                QMessageBox.critical(self, "Error", f"Error loading data: {e}")
            self.refresh()

    def exportData(self, export_module):
        file_types = getattr(export_module, 'file_types', 'All Files (*)')
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileName, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            "",
            file_types,
            options=options
        )
        export_module.export_data(self, fileName)

    def refresh(self):
        # Disable the buttons and file entries which will be enabled if the correct data are found in the datamixin
        md_functions = [self.closeAction,
                        self.MDReportButton, self.findSamplesButton]
        md_functions += self.md_export_actions
        md_functions += [value["button"]
                         for value in self.md_analyses.values()]

        [i.setEnabled(False) for i in md_functions]

        cd_functions = [self.CDReportButton, self.CustomReportButton]
        cd_functions += [value["button"]
                         for value in self.cd_analyses.values()]

        [i.setEnabled(False) for i in cd_functions]

        if not self.dataMixin.channel_df.empty:
            [i.setEnabled(True) for i in md_functions]
        if self.dataMixin.segments:
            [i.setEnabled(True) for i in cd_functions]

        self.updateFileLabels()

    def addFilePicker(self, layout, fileType: MeasurementFileType):
        # Create file picker layout
        fileLayout = QVBoxLayout()
        fileLabel = QLabel(f"{fileType.value} file:")
        self.fileLabels[fileType] = QLabel("No file selected")
        fileLayout.addWidget(fileLabel)
        fileLayout.addWidget(self.fileLabels[fileType])
        layout.addLayout(fileLayout)

    def updateFileLabels(self):
        for fileType, label in self.fileLabels.items():
            file_path = self.dataMixin.get_file_path(fileType)
            label_text = os.path.basename(file_path) if file_path else "No file selected"
            label.setText(label_text)

    def closeAll(self):
        self.dataMixin.reset()
        for window in self.windows:
            window.close()
        self.refresh()

    def openFindSamples(self):
        if self.findSamplesWindow is not None and not self.findSamplesWindow.isClosed:
            self.findSamplesWindow.raise_()
            self.findSamplesWindow.setWindowState(
                self.findSamplesWindow.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)

            self.findSamplesWindow.activateWindow()
        else:
            self.findSamplesWindow = FindSamplesWindow()
            self.findSamplesWindow.controller.updated.connect(self.refresh)
            self.findSamplesWindow.isClosed = False
            self.findSamplesWindow.show()
            self.findSamplesWindow.closed.connect(
                lambda: setattr(self.findSamplesWindow, 'isClosed', True))
            self.windows.append(self.findSamplesWindow)

        self.updateWindowsList()

    def openReport(self, window_type="MD"):
        newWindow = ReportWindow(self, window_type)
        self.add_window(newWindow)

    def updateWindowsList(self):
        self.windows = [
            window for window in self.windows if window.isVisible()]

    def add_window(self, newWindow):
        newWindow.show()
        self.windows.append(newWindow)
        self.updateWindowsList()

    def on_log_window_open(self):
        self.logWindow = openLogWindow(log_manager)

    def setupAnalysisButtons(self, layout):
        # MD Analysis
        mdLayout = QVBoxLayout()
        mdLabel = QLabel("MD Analysis")
        mdLayout.addWidget(mdLabel)

        self.md_analyses = settings.ANALYSES["MD"].copy()
        self.md_analyses["time_domain"]["callback"] = lambda: openTimeDomainAnalysis(
            self)
        self.md_analyses["spectrum"]["callback"] = lambda: openSpectrumAnalysis(
            self, window_type="MD")

        # self.md_analyses["cepstrum"]["callback"] = lambda: openCepstrumAnalysis(
        #     self, window_type="MD")
        self.md_analyses["coherence"]["callback"] = lambda: openCoherenceAnalysis(
            self, window_type="MD")
        self.md_analyses["spectrogram"]["callback"] = lambda: openSpectroGram(
            self, window_type="MD")
        self.md_analyses["channel_correlation"]["callback"] = lambda: openChannelCorrelation(
            self, window_type="MD")
        self.md_analyses["correlation_matrix"]["callback"] = lambda: openCorrelationMatrix(
            self, window_type="MD")
        self.md_analyses["formation"]["callback"] = lambda: openFormationAnalysis(
            self, window_type="MD")

        for analysis in self.md_analyses.values():
            button = QPushButton(analysis["label"], self)
            mdLayout.addWidget(button)
            if "callback" in analysis:
                button.clicked.connect(analysis["callback"])
            analysis["button"] = button

        mdLayout.addStretch(1)  # Add stretch to push everything to the top

        # CD Analysis
        cdLayout = QVBoxLayout()
        cdLabel = QLabel("CD Analysis")
        cdLayout.addWidget(cdLabel)

        self.findSamplesButton = QPushButton("Find samples", self)
        cdLayout.addWidget(self.findSamplesButton)
        self.findSamplesButton.clicked.connect(self.openFindSamples)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        cdLayout.addWidget(separator)

        self.cd_analyses = settings.ANALYSES["CD"].copy()
        self.cd_analyses["profile"]["callback"] = lambda: openCDProfileAnalysis(
            self, window_type="2d")
        self.cd_analyses["profile_waterfall"]["callback"] = lambda: openCDProfileAnalysis(
            self, window_type="waterfall")
        self.cd_analyses["spectrum"]["callback"] = lambda: openSpectrumAnalysis(
            self, window_type="CD")
        # self.md_analyses["cepstrum"]["callback"] = lambda: openCepstrumAnalysis(
        #     self, window_type="CD")
        self.cd_analyses["coherence"]["callback"] = lambda: openCoherenceAnalysis(
            self, window_type="CD")
        self.cd_analyses["spectrogram"]["callback"] = lambda: openSpectroGram(
            self, window_type="CD")
        self.cd_analyses["channel_correlation"]["callback"] = lambda: openChannelCorrelation(
            self, window_type="CD")
        self.cd_analyses["correlation_matrix"]["callback"] = lambda: openCorrelationMatrix(
            self, window_type="CD")
        self.cd_analyses["vca"]["callback"] = lambda: openVCA(self)
        self.cd_analyses["formation"]["callback"] = lambda: openFormationAnalysis(
            self, window_type="CD")

        for analysis in self.cd_analyses.values():
            button = QPushButton(analysis["label"], self)
            cdLayout.addWidget(button)
            if "callback" in analysis:
                button.clicked.connect(analysis["callback"])
            analysis["button"] = button

        cdLayout.addStretch(1)  # Add stretch to push everything to the top

        reportLayout = QVBoxLayout()
        reportLabel = QLabel("Reports")
        reportLayout.addWidget(reportLabel)

        self.MDReportButton = QPushButton("MD report", self)
        reportLayout.addWidget(self.MDReportButton)
        self.MDReportButton.clicked.connect(
            lambda: self.openReport(window_type="MD"))

        self.CDReportButton = QPushButton("CD report", self)
        reportLayout.addWidget(self.CDReportButton)
        self.CDReportButton.clicked.connect(
            lambda: self.openReport(window_type="CD"))

        self.CustomReportButton = QPushButton("Custom report", self)
        reportLayout.addWidget(self.CustomReportButton)

        reportLayout.addStretch(1)  # Add stretch to push everything to the top

        # Main layout for columns
        columnsLayout = QHBoxLayout()
        columnsLayout.addLayout(mdLayout)
        columnsLayout.addLayout(cdLayout)
        columnsLayout.addLayout(reportLayout)

        layout.addLayout(columnsLayout)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow Ctrl+C to exit as usual
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Format traceback
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_manager.handle_crash(tb)

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
