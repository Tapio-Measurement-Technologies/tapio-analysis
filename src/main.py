# Tapio Analysis
# Copyright 2024 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.


import settings
import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QMessageBox,
                             QMainWindow, QFileDialog, QFrame, QStyleFactory)
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtCore import Qt

from gui.find_samples import FindSamplesWindow
from gui.report import ReportWindow
import os

from utils.data_loader import DataMixin
from utils.windows import *
from utils.dynamic_loader import load_modules_from_folder

import logging
import os

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class MainWindow(QMainWindow, DataMixin):

    def __init__(self):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.windows = []
        self.findSamplesWindow = None

        base_path = os.path.dirname(os.path.abspath(__file__))
        self.loaders = load_modules_from_folder(os.path.join(base_path, 'loaders'))
        self.exporters = load_modules_from_folder(os.path.join(base_path, 'exporters'))

        self.md_export_actions = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Tapio Analysis')
        self.setGeometry(200, 200, 800, 600)  # x, y, width, height

        # Menu
        mainMenu = self.menuBar()
        fileMenu = mainMenu.addMenu('File')

        # Create menu items for each loaded module
        for module_name, module in self.loaders.items():
            action_text = getattr(module, 'menu_text', module_name)
            action = QAction(action_text, self)
            action.triggered.connect(lambda checked, module=module: self.loadFiles(module))
            fileMenu.addAction(action)

            if len(self.loaders.items()) == 1:
                action.setShortcut('Ctrl+O')

        # Create menu items for export module
        for module_name, module in self.exporters.items():
            action_text = getattr(module, 'menu_text', module_name)
            action = QAction(action_text, self)
            action.triggered.connect(lambda checked, module=module: self.exportData(module))
            fileMenu.addAction(action)

            if len(self.loaders.items()) == 1:
                action.setShortcut('Ctrl+E')

            if module_name.startswith('md'):
                self.md_export_actions.append(action)

        self.closeAction = QAction('Close open files', self)
        self.closeAction.triggered.connect(self.closeAll)
        self.closeAction.setStatusTip("Close all open files")
        fileMenu.addAction(self.closeAction)

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
        for fileType in ["Header", "Calibration", "Data", "Paper machine", "Sample locations"]:
            self.addFilePicker(logoLayout, fileType)

        # Add the logo and file pickers layout to the main layout
        layout.addLayout(logoLayout)

        # Analysis Buttons
        self.setupAnalysisButtons(layout)
        self.refresh()

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
            loader_module.load_data(self, fileNames)
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

    def addFilePicker(self, layout, fileType):
        # Create file picker layout
        fileLayout = QVBoxLayout()
        fileLabel = QLabel(f"{fileType} file:")
        self.fileLabels[fileType] = QLabel("No file selected")
        fileLayout.addWidget(fileLabel)
        fileLayout.addWidget(self.fileLabels[fileType])
        layout.addLayout(fileLayout)

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
        self.MDReportButton.clicked.connect(lambda: self.openReport(window_type="MD"))

        self.CDReportButton = QPushButton("CD report", self)
        reportLayout.addWidget(self.CDReportButton)
        self.CDReportButton.clicked.connect(lambda: self.openReport(window_type="CD"))

        self.CustomReportButton = QPushButton("Custom report", self)
        reportLayout.addWidget(self.CustomReportButton)

        reportLayout.addStretch(1)  # Add stretch to push everything to the top

        # Main layout for columns
        columnsLayout = QHBoxLayout()
        columnsLayout.addLayout(mdLayout)
        columnsLayout.addLayout(cdLayout)
        columnsLayout.addLayout(reportLayout)

        layout.addLayout(columnsLayout)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(
        QIcon(os.path.join(settings.ASSETS_DIR, "tapio_icon.ico")))

    app.setStyle(QStyleFactory.create('Fusion'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    # main_debug()
    main()
