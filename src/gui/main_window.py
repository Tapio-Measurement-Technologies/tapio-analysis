# Tapio Analysis
# Copyright 2024 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QMessageBox,
                             QMainWindow, QFileDialog)
from PyQt6.QtGui import QPixmap, QAction
from PyQt6.QtCore import Qt
import os

from gui.find_samples import FindSamplesWindow
from gui.report import ReportWindow
from gui.log_window import LogWindow
from gui.setting_input_dialog import open_setting_input_dialog
from utils.types import LoaderModule, ExporterModule
from utils.measurement import Measurement, MeasurementFileType
from utils import store
import settings

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.windows = []
        self.findSamplesWindow = None
        self.logWindow = None

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
            store.loaders.items(),
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
        for module_name, module in store.exporters.items():
            action_text = getattr(module, 'menu_text', module_name)
            action = QAction(action_text, self)
            action.triggered.connect(
                lambda checked, module=module: self.exportData(module))
            fileMenu.addAction(action)

            if len(store.exporters.items()) == 1:
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
        set_settings_action.triggered.connect(lambda: open_setting_input_dialog(self))
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

    def loadFiles(self, loader_module: LoaderModule):
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
                store.loaded_measurement = loader_module.load_data(fileNames)
            except Exception as e:
                store.loaded_measurement = None
                QMessageBox.critical(self, "Error", f"Error loading data: {e}")
            self.refresh()

    def exportData(self, export_module: ExporterModule):
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
        if fileName:
            export_module.export_data(fileName)

    def refresh(self):
        main_window_modules = [module for section in settings.ANALYSIS_SECTIONS for module in section.modules]
        measurement_loaded = store.loaded_measurement is not None
        # Disable the buttons and file entries which will be enabled if the correct data are found in the measurement
        md_functions = [self.closeAction]
        md_functions += self.md_export_actions
        md_functions += [module.button for module in main_window_modules if module.type == "MD"]
        cd_functions = [module.button for module in main_window_modules if module.type == "CD"]
        other_functions = [module.button for module in main_window_modules if module.type not in ["MD", "CD"]]

        [i.setEnabled(False) for i in md_functions]
        [i.setEnabled(False) for i in cd_functions]
        [i.setEnabled(False) for i in other_functions]

        if measurement_loaded and not store.loaded_measurement.channel_df.empty:
            [i.setEnabled(True) for i in md_functions]
        if measurement_loaded and store.loaded_measurement.segments:
            [i.setEnabled(True) for i in cd_functions]
        if measurement_loaded:
            [i.setEnabled(True) for i in other_functions]

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
            file_path = (store.loaded_measurement or Measurement()).get_file_path(fileType)
            label_text = os.path.basename(file_path) if file_path else "No file selected"
            label.setText(label_text)

    def closeAll(self):
        store.loaded_measurement = None
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
            self.findSamplesWindow = FindSamplesWindow(measurement=store.loaded_measurement)
            self.findSamplesWindow.controller.updated.connect(self.refresh)
            self.findSamplesWindow.isClosed = False
            self.findSamplesWindow.show()
            self.findSamplesWindow.closed.connect(
                lambda: setattr(self.findSamplesWindow, 'isClosed', True))
            self.windows.append(self.findSamplesWindow)

        self.updateWindowsList()

    def openReport(self, window_type="MD"):
        newWindow = ReportWindow(self, store.loaded_measurement, window_type)
        self.add_window(newWindow)

    def updateWindowsList(self):
        self.windows = [
            window for window in self.windows if window.isVisible()]

    def add_window(self, newWindow):
        newWindow.show()
        self.windows.append(newWindow)
        self.updateWindowsList()

    def on_log_window_open(self):
        self.logWindow = LogWindow()
        self.logWindow.show()

    def open_analysis_window(self, analysis_name, window_type):
        analysis = store.analyses.get(analysis_name, None)
        if not analysis:
            print(f"Error: Analysis '{analysis_name}' not found")
            return
        newWindow = analysis.AnalysisWindow(measurement=store.loaded_measurement, window_type=window_type)
        self.add_window(newWindow)

    def setupAnalysisButtons(self, layout):
        columnsLayout = QHBoxLayout()
        for section in settings.ANALYSIS_SECTIONS:
            section_layout = QVBoxLayout()
            section_label = QLabel(section.name)
            section_layout.addWidget(section_label)

            for module in section.modules:
                analysis = store.analyses.get(module.module_name, None)

                # Use the override analysis_name if provided, otherwise use the one from the module
                if module.analysis_name:
                    button_title = module.analysis_name
                else:
                    button_title = analysis.analysis_name if analysis else module.module_name

                button = QPushButton(button_title, self)

                # Create a function that captures the current module value
                def create_callback(mod=module):
                    if mod.callback:
                        return lambda _: mod.callback(**(mod.arguments or {}))
                    elif mod.callback_name and hasattr(self, mod.callback_name):
                        # Call the method on self using the callback_name with arguments
                        return lambda _: getattr(self, mod.callback_name)(**(mod.arguments or {}))
                    else:
                        return lambda _: self.open_analysis_window(mod.module_name, mod.type)

                button.clicked.connect(create_callback())
                section_layout.addWidget(button)
                module.button = button

            section_layout.addStretch(1)
            columnsLayout.addLayout(section_layout)

        layout.addLayout(columnsLayout)