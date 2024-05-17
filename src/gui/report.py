from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSizePolicy, QPushButton, QScrollArea, QFrame, QLineEdit, QFileDialog, QMenuBar)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QAction
from utils.data_loader import DataMixin
from controllers import *
from utils.windows import *
import settings
import datetime
from docx import Document
from docx.shared import Mm, Cm, Pt
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
import numpy as np
import json

class ReportWindow(QWidget, DataMixin):
    def __init__(self, main_window, window_type="MD"):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.setWindowTitle(f"Generate {window_type} Report ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)
        self.main_window = main_window
        self.window_type = window_type
        self.report_title = f"{window_type} Report"
        self.section_widgets = []

        # Main layout
        self.main_layout = QVBoxLayout()
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.main_layout)

        # Menu
        self.initMenuBar(self.main_layout)

        # Title input
        self.title_layout = QVBoxLayout()
        self.title_label = QLabel("Report Title:")
        self.title_input = QLineEdit(self.report_title)
        self.title_input.textEdited.connect(self.update_report_title)
        self.title_layout.addWidget(self.title_label)
        self.title_layout.addWidget(self.title_input)
        self.main_layout.addLayout(self.title_layout)

        # Scroll area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.main_layout.addWidget(self.scroll_area)

        # Widget inside scroll area
        self.scroll_widget = QWidget()
        self.scroll_area.setWidget(self.scroll_widget)

        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Heading
        heading = QLabel("Sections")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_layout.addWidget(heading)

        # Container for sections
        self.sections_container = QVBoxLayout()
        self.sections_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.addLayout(self.sections_container)

        # Button for adding sections
        self.add_section_button = QPushButton("+ Add section")
        self.add_section_button.clicked.connect(lambda: self.add_section())
        self.scroll_layout.addWidget(self.add_section_button)

        # Generate Report Button
        self.generate_report_button = QPushButton("Generate Report")
        self.generate_report_button.clicked.connect(self.generate_report)
        self.main_layout.addWidget(self.generate_report_button)

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.addWidget(menuBar, 0)

        fileMenu = menuBar.addMenu('File')
        loadFileAction = QAction('Load from JSON', self)
        loadFileAction.setShortcut("Ctrl+O")
        loadFileAction.setStatusTip("Open file")
        loadFileAction.triggered.connect(self.load_from_json)
        fileMenu.addAction(loadFileAction)

    def add_section(self, section_name = "Section"):
        section_widget = ReportSectionWidget(self.main_window, section_name, self.window_type)
        self.section_widgets.append(section_widget)
        section_widget.destroyed.connect(lambda: self.section_widgets.remove(section_widget))
        self.sections_container.addWidget(section_widget)
        return section_widget

    def update_report_title(self, title):
        self.report_title = title
        self.title_input.setText(self.report_title)

    def generate_report(self):
        doc = Document()
        margin = Cm(1)
        for section in doc.sections:
            section.top_margin = margin
            section.bottom_margin = margin
            section.left_margin = margin
            section.right_margin = margin
        doc.add_heading(self.report_title, 0)
        doc.add_paragraph(f"Generated {str(datetime.datetime.now())}")

        def get_text_width(document):
            """
            Returns the text width in mm.
            """
            section = document.sections[0]
            return (section.page_width - section.left_margin - section.right_margin) / 36000

        for section in self.section_widgets:
            doc.add_heading(section.section_name)
            for analysis in section.analysis_widgets:
                doc.add_heading(f"{analysis.analysis_name} {analysis.get_channel_text()}", 2)

                # Add table with image and stats table
                img_col_width = Mm(get_text_width(doc) * (3/5))
                stats_col_width = Mm(get_text_width(doc) * (2/5))
                table = doc.add_table(rows=1, cols=2)
                table.autofit = True

                col1 = table.columns[0]
                col1.width = img_col_width
                cell1 = table.cell(0, 0)
                cell1.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                paragraph = cell1.paragraphs[0]
                run = paragraph.add_run()
                run.add_picture(analysis.controller.getPlotImage(), width=Cm(col1.width.cm - 0.5))

                cell2 = table.cell(0, 1)
                col2 = table.columns[1]
                col2.width = stats_col_width
                cell2.width = stats_col_width

                data = analysis.controller.getStatsTableData()
                shape = np.shape(data)
                if len(shape) == 2:
                    rows, cols = shape
                elif len(shape) == 1:
                    rows = shape[0]
                    cols = 1
                else:
                    rows = 1
                    cols = 1
                stats_table = cell2.add_table(rows, cols)

                for row_idx, row_data in enumerate(data):
                    row = stats_table.rows[row_idx]
                    for col_idx, cell_data in enumerate(row_data):
                        cell = row.cells[col_idx]
                        cell.paragraphs[0].text = cell_data
                        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                        cell.paragraphs[0].style.font.size = Pt(10)
                        cell.paragraphs[0].style.font.name = "Nimbus Mono PS"

        # Open save file dialog
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileName, _ = QFileDialog.getSaveFileName(
            self, "Word Document", "", "DOCX Files (*.docx)", options=options)
        if fileName:
            if not fileName.endswith('.docx'):
                fileName += '.docx'
            doc.save(fileName)
            self.close()

    def load_from_json(self):
        for section_widget in self.section_widgets:
            section_widget.remove_self()
        dialog = QFileDialog(self)
        options = QFileDialog.options(dialog)
        fileName, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Files (*);;JSON files (*.json)",
            options=options)
        if fileName:
            with open(fileName, 'r') as file:
                try:
                    data = json.load(file)
                    self.update_report_title(data["report_title"])
                    sections = data["sections"][self.window_type]
                    for section in sections:
                        section_name = section["section_name"]
                        section_widget = self.add_section(section_name)
                        analyses = section["analyses"]
                        for analysis in analyses:
                            analysis_name = settings.ANALYSES[self.window_type][analysis["analysis"]]["label"]
                            widget = AnalysisWidget(self.main_window, analysis_name, self.window_type)
                            if "channel" in analysis:
                                widget.controller.channel = analysis["channel"]
                            if "channel1" in analysis:
                                widget.controller.channel1 = analysis["channel1"]
                            if "channel2" in analysis:
                                widget.controller.channel2 = analysis["channel2"]
                            if "analysis_range_low" in analysis:
                                widget.controller.analysis_range_low = analysis["analysis_range_low"]
                            if "analysis_range_high" in analysis:
                                widget.controller.analysis_range_high = analysis["analysis_range_high"]
                            if "band_pass_low" in analysis:
                                widget.controller.band_pass_low = analysis["band_pass_low"]
                            if "band_pass_high" in analysis:
                                widget.controller.band_pass_high = analysis["band_pass_high"]
                            if "show_individual_profiles" in analysis:
                                widget.controller.show_profiles = analysis["show_individual_profiles"]
                            if "show_min_max" in analysis:
                                widget.controller.show_min_max = analysis["show_min_max"]
                            if "show_legend" in analysis:
                                widget.controller.show_legend = analysis["show_legend"]
                            if "show_wavelength_labels" in analysis:
                                widget.controller.show_wavelength = analysis["show_wavelength_labels"]
                            if "show_unfiltered_data" in analysis:
                                widget.controller.show_unfiltered_data = analysis["show_unfiltered_data"]
                            if "machine_speed" in analysis:
                                widget.controller.machine_speed = analysis["machine_speed"]
                            if "frequency_range_low" in analysis:
                                widget.controller.frequency_range_low = analysis["frequency_range_low"]
                            if "frequency_range_high" in analysis:
                                widget.controller.frequency_range_high = analysis["frequency_range_high"]
                            if "selected_frequency" in analysis:
                                widget.controller.selected_freq = analysis["selected_frequency"]
                            if "nperseg" in analysis:
                                widget.controller.nperseg = analysis["nperseg"]
                            widget.preview_window.refresh()
                            section_widget.add_analysis(widget)
                except:
                    print("Error loading JSON file")

    def closeEvent(self, event):
        for widget in self.section_widgets:
            widget.remove_self()
        event.accept()

class ReportSectionWidget(QFrame):
    def __init__(self, main_window, section_name="Section", window_type="MD"):
        super().__init__()
        self.main_window = main_window
        self.section_name = section_name
        self.window_type = window_type
        self.analysis_widgets = []

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Plain)
        self.setLineWidth(1)

        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(self.layout)

        # Horizontal layout for heading and remove button
        heading_layout = QHBoxLayout()
        self.layout.addLayout(heading_layout)

        self.section_name_label = QLabel("Section name:")
        heading_layout.addWidget(self.section_name_label)

        # Remove button for section
        self.remove_button = QPushButton("Remove section")
        self.remove_button.clicked.connect(self.remove_self)
        heading_layout.addWidget(self.remove_button)

        # Section name input
        self.section_name_input = QLineEdit(self.section_name)
        self.section_name_input.textEdited.connect(self.update_section_name)
        self.section_name_input.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.section_name_input)

        self.analyses_label = QLabel("Included analyses:")
        self.layout.addWidget(self.analyses_label)

        # Container for analyses
        self.analyses_container = QVBoxLayout()
        self.analyses_container.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.addLayout(self.analyses_container)

        # ComboBox for analysis items
        self.analysis_combobox = QComboBox()
        self.analyses = settings.ANALYSES[self.window_type]
        labels = [analysis["label"] for analysis in self.analyses.values()]
        self.setup_combobox(self.analysis_combobox, labels)
        self.analysis_combobox.currentIndexChanged.connect(self.add_new_analysis)
        self.layout.addWidget(self.analysis_combobox)

    def update_section_name(self, name):
        self.section_name = name

    def setup_combobox(self, combobox, items):
        model = QStandardItemModel()
        add_item = QStandardItem("Add analysis")
        model.appendRow(add_item)
        combobox.insertSeparator(1)

        for item in items:
            model.appendRow(QStandardItem(item))

        combobox.setModel(model)
        combobox.setCurrentIndex(0)

    def add_new_analysis(self):
        if self.analysis_combobox.currentIndex() == 0:
            return

        analysis_name = self.analysis_combobox.currentText()
        if analysis_name:  # Ensure a valid analysis is selected
            analysis_widget = AnalysisWidget(self.main_window, analysis_name, self.window_type)
            self.analysis_widgets.append(analysis_widget)
            analysis_widget.destroyed.connect(lambda: self.analysis_widgets.remove(analysis_widget))
            self.analyses_container.addWidget(analysis_widget)
            # Optionally clear the combo box to prevent adding the same analysis again
            self.analysis_combobox.setCurrentIndex(0)

    def add_analysis(self, analysis_widget):
        self.analysis_widgets.append(analysis_widget)
        analysis_widget.destroyed.connect(lambda: self.analysis_widgets.remove(analysis_widget))
        self.analyses_container.addWidget(analysis_widget)

    def remove_self(self):
        for widget in self.analysis_widgets:
            widget.remove_self()
        self.setParent(None)
        self.deleteLater()

class AnalysisWidget(QWidget):
    def __init__(self, main_window, analysis_name, window_type="MD"):
        super().__init__()
        self.analysis_name = analysis_name
        self.window_type = window_type
        self.main_window = main_window
        self.analyses = settings.ANALYSES

        if self.window_type == "CD":
            if analysis_name == self.analyses[self.window_type]["profile"]["label"]:
                window_type = "2d"
                self.controller = CDProfileController(window_type)
                self.preview_window = CDProfileWindow(window_type, self.controller)

            elif analysis_name == self.analyses[self.window_type]["profile_waterfall"]["label"]:
                window_type = "waterfall"
                self.controller = CDProfileController(window_type)
                self.preview_window = CDProfileWindow(window_type, self.controller)

            elif analysis_name == self.analyses[self.window_type]["vca"]["label"]:
                self.controller = VCAController()
                self.preview_window = VCAWindow(self.controller)

        elif self.window_type == "MD":
            if analysis_name == self.analyses[self.window_type]["time_domain"]["label"]:
                self.controller = TimeDomainController()
                self.preview_window = TimeDomainWindow(self.controller)

        if analysis_name == self.analyses[self.window_type]["spectrum"]["label"]:
            self.controller = SpectrumController(self.window_type)
            self.preview_window = SpectrumWindow(self.window_type, self.controller)

        elif analysis_name == self.analyses[self.window_type]["spectrogram"]["label"]:
            self.controller = SpectrogramController(self.window_type)
            self.preview_window = SpectrogramWindow(self.window_type, self.controller)

        elif analysis_name == self.analyses[self.window_type]["channel_correlation"]["label"]:
            self.controller = ChannelCorrelationController(self.window_type)
            self.preview_window = ChannelCorrelationWindow(self.window_type, self.controller)

        elif analysis_name == self.analyses[self.window_type]["correlation_matrix"]["label"]:
            self.controller = CorrelationMatrixController(self.window_type)
            self.preview_window = CorrelationMatrixWindow(self.window_type, self.controller)

        elif analysis_name == self.analyses[self.window_type]["formation"]["label"]:
            self.controller = FormationController(self.window_type)
            self.preview_window = FormationWindow(self.window_type, self.controller)

        if self.controller:
            self.controller.updated.connect(self.update_analysis_label)

        self.layout = QHBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.layout)

        # Analysis label
        self.analysis_label = QLabel(f"{self.analysis_name} {self.get_channel_text()}")
        self.analysis_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.analysis_label)

        # Button layout to align buttons to the right
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.preview_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        if self.preview:
            self.preview_button.clicked.connect(self.preview)
        button_layout.addWidget(self.preview_button)

        # Remove button for analysis
        self.remove_button = QPushButton("Remove")
        self.remove_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.remove_button.clicked.connect(self.remove_self)
        button_layout.addWidget(self.remove_button)

        self.layout.addLayout(button_layout)

    def get_channel_text(self):
        if hasattr(self.controller, "channel"):
            return f"({self.controller.channel})"
        elif hasattr(self.controller, "channel1") and hasattr(self.controller, "channel2"):
            return f"({self.controller.channel1}, {self.controller.channel2})"
        else:
            return ""

    def update_analysis_label(self):
        self.analysis_label.setText(f"{self.analysis_name} {self.get_channel_text()}")

    def preview(self):
        if not self.preview_window:
            return
        if self.preview_window.isVisible():
            self.preview_window.activateWindow()
        else:
            self.preview_window.show()
            self.main_window.windows.append(self.preview_window)
            self.main_window.updateWindowsList()

    def remove_self(self):
        if self.preview_window:
            self.preview_window.close()
        self.setParent(None)
        self.deleteLater()