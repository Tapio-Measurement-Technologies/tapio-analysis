from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSizePolicy,
                             QPushButton, QScrollArea, QFrame, QLineEdit, QFileDialog, QMenuBar, QTextEdit, QMessageBox, QInputDialog)

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QAction
import settings
from utils.report_generator import create_report_generator
import os
from customizations import apply_plot_customizations
import traceback
import importlib.util
from utils import store
from utils.measurement import Measurement

analysis_name_mapping = {
    module_name: analysis.analysis_name
    for module_name, analysis in store.analyses.items()
}

module_name_mapping = {
    v: k for k, v in analysis_name_mapping.items()
}

class Editor(QTextEdit):
    def __init__(self):
        super().__init__()
        self.textChanged.connect(self.autoResize)

    def autoResize(self):
        self.document().setTextWidth(self.viewport().width())
        margins = self.contentsMargins()
        height = int(self.document().size().height() +
                     margins.top() + margins.bottom())
        self.setFixedHeight(height)

    def resizeEvent(self, event):
        self.autoResize()


class ReportWindow(QWidget):
    def __init__(self, main_window, measurement: Measurement, window_type="MD"):
        super().__init__()
        self.setWindowTitle(f"Generate {window_type} Report ({
                            measurement.measurement_label})")
        self.resize(*settings.REPORT_WINDOW_SIZE)

        self.measurement = measurement
        self.main_window = main_window
        self.window_type = window_type
        self.report_title = f"{window_type} Report"
        self.report_subtitle = f"Mill PM 1"
        self.section_widgets = []
        self.header_image_path = settings.REPORT_LOGO_PATH
        if self.window_type == "CD":
            self.sample_image_path = settings.CD_REPORT_SAMPLE_IMAGE_PATH
        elif self.window_type == "MD":
            self.sample_image_path = settings.MD_REPORT_SAMPLE_IMAGE_PATH

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

        # Title input
        self.subtitle_layout = QVBoxLayout()
        self.subtitle_label = QLabel("Report subtitle:")
        self.subtitle_input = QLineEdit(self.report_subtitle)
        self.subtitle_input.textEdited.connect(self.update_report_subtitle)
        self.subtitle_layout.addWidget(self.subtitle_label)
        self.subtitle_layout.addWidget(self.subtitle_input)
        self.main_layout.addLayout(self.subtitle_layout)

        # Additional information input
        self.additional_info_layout = QVBoxLayout()
        self.additional_info_label = QLabel("Additional Information:")
        self.additional_info_input = Editor()
        self.additional_info_input.setText(
            settings.REPORT_ADDITIONAL_INFO_DEFAULT)
        self.additional_info_input.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.additional_info_layout.addWidget(self.additional_info_label)
        self.additional_info_layout.addWidget(self.additional_info_input)
        self.main_layout.addLayout(self.additional_info_layout)

        # Image input
        self.header_image_layout = QHBoxLayout()
        self.header_image_label = QLabel("Logo image:")
        self.header_image_path_input = QLineEdit(self.header_image_path)
        self.header_image_path_button = QPushButton("Choose Image")
        self.header_image_path_button.clicked.connect(self.choose_image)
        self.header_image_layout.addWidget(self.header_image_label)
        self.header_image_layout.addWidget(self.header_image_path_input)
        self.header_image_layout.addWidget(self.header_image_path_button)
        self.main_layout.addLayout(self.header_image_layout)

        # Image input
        self.sample_image_layout = QHBoxLayout()
        self.sample_image_label = QLabel("Sample image:")
        self.sample_image_path_input = QLineEdit(self.sample_image_path)
        self.sample_image_path_button = QPushButton("Choose Image")
        self.sample_image_path_button.clicked.connect(self.choose_image)
        self.sample_image_layout.addWidget(self.sample_image_label)
        self.sample_image_layout.addWidget(self.sample_image_path_input)
        self.sample_image_layout.addWidget(self.sample_image_path_button)
        self.main_layout.addLayout(self.sample_image_layout)

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

        if self.window_type == "MD":
            speed, ok = QInputDialog.getDouble(
                self,
                "Paper machine speed",
                "Enter paper machine speed (m/min):",
                settings.PAPER_MACHINE_SPEED_DEFAULT,
                0,
                10000,
                2
            )
            if not ok:
                self.close()
                return
            settings.PAPER_MACHINE_SPEED_DEFAULT = speed

        if self.window_type == "MD":
            if settings.MD_REPORT_TEMPLATE_DEFAULT:
                self.load_from_python(settings.MD_REPORT_TEMPLATE_DEFAULT)

        if self.window_type == "CD":
            if settings.CD_REPORT_TEMPLATE_DEFAULT:
                self.load_from_python(settings.CD_REPORT_TEMPLATE_DEFAULT)

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)

        fileMenu = menuBar.addMenu('File')
        loadFileAction = QAction('Load report template', self)
        loadFileAction.setShortcut("Ctrl+O")
        loadFileAction.setStatusTip("Open file")
        loadFileAction.triggered.connect(self.load_from_python)
        fileMenu.addAction(loadFileAction)

    def add_section(self, section_name="Section"):
        section_widget = ReportSectionWidget(
            self.main_window, self.measurement, section_name, self.window_type)
        self.section_widgets.append(section_widget)
        section_widget.destroyed.connect(
            lambda: self.section_widgets.remove(section_widget))
        self.sections_container.addWidget(section_widget)
        return section_widget

    def update_report_title(self, title):
        self.report_title = title
        self.title_input.setText(self.report_title)

    def update_report_subtitle(self, subtitle):
        self.report_subtitle = subtitle
        self.subtitle_input.setText(self.report_subtitle)

    def choose_image(self):
        dialog = QFileDialog(self)
        options = QFileDialog.options(dialog)
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Choose Image", "", "Image Files (*.png *.jpg *.bmp *.gif)", options=options)
        if file_name:
            self.header_image_path = file_name
            self.header_image_path_input.setText(file_name)

    def generate_report(self):
        # Prepare report data
        report_data = {
            'title': self.report_title,
            'subtitle': self.report_subtitle,
            'additional_info': self.additional_info_input.toPlainText(),
            'header_image_path': self.header_image_path,
            'sample_image_path': self.sample_image_path,
            'sections': self.section_widgets,
            'window_type': self.window_type
        }

        # Get selected format
        report_format = settings.REPORT_FORMAT
        # Create appropriate generator
        try:
            generator = create_report_generator(report_format, report_data)

            # Open save file dialog with appropriate extension
            dialog = QFileDialog()
            options = QFileDialog.options(dialog)

            if report_format == 'word':
                file_filter = "Word Document (*.docx)"
                default_ext = '.docx'
            else:  # latex
                file_filter = "LaTeX Document (*.tex)"
                default_ext = '.tex'

            fileName, _ = QFileDialog.getSaveFileName(
                self, "Save Report", "", file_filter, options=options)

            if fileName:
                if not fileName.endswith(default_ext):
                    fileName += default_ext

                # Generate report
                generator.generate(fileName)

                self.close()
                print(
                    f"Report successfully generated as {os.path.basename(fileName)}")
                QMessageBox.information(self, "Success",
                                        f"Report successfully generated to '{fileName}'")

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to generate report:\n{str(e)}\n\nSee console for details.")
            traceback.print_exc()

    def load_from_python(self, fileName=None):
        errors = []

        for section_widget in self.section_widgets:
            section_widget.remove_self()

        if not fileName:
            dialog = QFileDialog(self)
            options = QFileDialog.options(dialog)
            fileName, _ = QFileDialog.getOpenFileName(
                self,
                "Open Python File",
                "",
                "Python files (*.py);;All Files (*);;",
                options=options
            )

        if fileName:
            try:
                # Load the Python file as a module dynamically
                module_name = os.path.splitext(os.path.basename(fileName))[0]
                spec = importlib.util.spec_from_file_location(
                    module_name, fileName)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Extract expected variables
                if not hasattr(module, "report_title") or not hasattr(module, "sections"):
                    raise ValueError(
                        "Python file must define 'report_title' and 'sections'")

                self.update_report_title(module.report_title)
                self.update_report_subtitle(module.report_subtitle)

                # Set additional info if it exists in the template
                if hasattr(module, "additional_info"):
                    self.additional_info_input.setText(module.additional_info)
                else:
                    self.additional_info_input.setText(settings.REPORT_ADDITIONAL_INFO_DEFAULT)

                sections = module.sections

                for section in sections:
                    section_name = section.get("section_name")
                    section_widget = self.add_section(section_name)
                    analyses = section.get("analyses", [])

                    for analysis in analyses:
                        analysis_module_name = analysis.get("analysis")

                        channel = analysis.get("channel", "")
                        channel2 = analysis.get("channel2", "")

                        invalid_channel = any(
                            c and c not in self.measurement.channels for c in [channel, channel2]
                        )

                        if invalid_channel:
                            errors.append(
                                f"{section_name}/{analysis_module_name}: Invalid channel name '{channel}'{f' or {channel2}' if channel2 else ''}"
                            )
                            continue

                        widget = AnalysisWidget(
                            self.main_window,
                            analysis_module_name,
                            self.measurement,
                            self.window_type,
                            analysis_title=analysis.get("analysis_title"),
                            info_string=analysis.get("info_string"),
                            report_layout=analysis.get("report_layout"),
                            image_width_mm=analysis.get("image_width_mm")
                        )

                        # Assign attributes if they exist, note the naming must be same as class attribute
                        for attr in [
                            "channel", "channel2",
                            "analysis_range_low", "analysis_range_high",
                            "band_pass_low", "band_pass_high",
                            "show_individual_profiles", "show_min_max", "show_legend",
                            "show_wavelength_labels", "show_unfiltered_data",
                            "machine_speed", "frequency_range_low", "frequency_range_high",
                            "selected_frequencies", "nperseg", "peak_detection_range_min", "peak_detection_range_max"
                        ]:
                            if attr in analysis:
                                setattr(widget.controller,
                                        attr, analysis[attr])

                        widget.preview_window.refresh()
                        section_widget.add_analysis(widget)

            except Exception as e:
                traceback.print_exc()
                errors.append(str(e))
            if errors:
                show_load_error_msgbox(errors)

    def closeEvent(self, event):
        for widget in self.section_widgets:
            widget.remove_self()
        event.accept()


class ReportSectionWidget(QFrame):
    def __init__(self, main_window, measurement: Measurement, section_name="Section", window_type="MD"):
        super().__init__()
        self.main_window = main_window
        self.section_name = section_name
        self.window_type = window_type
        self.measurement = measurement
        self.analysis_widgets = []

        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Plain)
        self.setLineWidth(1)

        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(10, 10, 10, 10)
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
        # Disable wheel scrolling to prevent accidental selections when scrolling the report window
        self.analysis_combobox.wheelEvent = lambda event: None
        self.analyses = {
            module_name: {
                "label": analysis.analysis_name
            }
            for module_name, analysis in store.analyses.items()
            if window_type in analysis.analysis_types and module_name not in settings.ANALYSES_EXCLUDED_FROM_REPORT
        }
        labels = [analysis["label"] for analysis in self.analyses.values()]
        self.setup_combobox(self.analysis_combobox, labels)
        self.analysis_combobox.currentIndexChanged.connect(
            self.add_new_analysis)
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
        analysis_module_name = module_name_mapping[analysis_name]
        if analysis_name:  # Ensure a valid analysis is selected
            analysis_widget = AnalysisWidget(
                self.main_window, analysis_module_name, self.measurement, self.window_type)
            self.analysis_widgets.append(analysis_widget)
            analysis_widget.destroyed.connect(
                lambda: self.analysis_widgets.remove(analysis_widget))
            self.analyses_container.addWidget(analysis_widget)
            # Optionally clear the combo box to prevent adding the same analysis again
            self.analysis_combobox.setCurrentIndex(0)

    def add_analysis(self, analysis_widget):
        self.analysis_widgets.append(analysis_widget)
        analysis_widget.destroyed.connect(
            lambda: self.analysis_widgets.remove(analysis_widget))
        self.analyses_container.addWidget(analysis_widget)

    def remove_self(self):
        for widget in self.analysis_widgets:
            widget.remove_self()
        self.setParent(None)
        self.deleteLater()


class AnalysisWidget(QWidget):
    def __init__(self, main_window, analysis_name, measurement, window_type="MD", analysis_title=None, info_string=None, report_layout=None, image_width_mm=None):
        super().__init__()
        self.analysis_name = analysis_name
        self.window_type = window_type
        self.main_window = main_window
        self.measurement = measurement
        self.analysis_title = analysis_title
        self.info_string = info_string
        self.report_layout = report_layout
        self.image_width_mm = image_width_mm

        self.controller = store.analyses[analysis_name].AnalysisController(self.measurement, self.window_type)
        self.preview_window = store.analyses[analysis_name].AnalysisWindow(self.controller, self.window_type)
        self.preview_window.show()
        self.preview_window.hide()

        if self.controller:
            self.controller.updated.connect(self.update_analysis_label)
            self.controller.updated.connect(
                lambda: apply_plot_customizations(self))
            apply_plot_customizations(self)

        self.layout = QHBoxLayout()
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.layout)

        # Analysis label
        analysis_label_text = self.analysis_title or f"{
            analysis_name_mapping[self.analysis_name]} {self.get_channel_text()}"

        self.analysis_label = QLabel(analysis_label_text)
        self.analysis_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.analysis_label)

        # Button layout to align buttons to the right
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Preview button
        self.preview_button = QPushButton("Preview")
        self.preview_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        if self.preview:
            self.preview_button.clicked.connect(self.preview)
        button_layout.addWidget(self.preview_button)

        # Remove button for analysis
        self.remove_button = QPushButton("Remove")
        self.remove_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.remove_button.clicked.connect(self.remove_self)
        button_layout.addWidget(self.remove_button)

        self.layout.addLayout(button_layout)

        # Just refresh the window content without showing it
        self.preview_window.refresh()

    def get_channel_text(self):
        if hasattr(self.controller, "channel"):
            return f"({self.controller.channel})"
        elif hasattr(self.controller, "channel") and hasattr(self.controller, "channel2"):
            return f"({self.controller.channel}, {self.controller.channel2})"
        else:
            return ""

    def update_analysis_label(self):
        self.analysis_label.setText(f"{analysis_name_mapping[self.analysis_name]} {
                                    self.get_channel_text()}")

    def preview(self):
        if not self.preview_window:
            return
        if self.preview_window.isVisible():
            self.preview_window.activateWindow()
        else:
            self.main_window.add_window(self.preview_window)

    def remove_self(self):
        if self.preview_window:
            self.preview_window.close()
        self.setParent(None)
        self.deleteLater()


def delete_paragraph(paragraph):
    p = paragraph._element
    p.getparent().remove(p)
    paragraph._p = paragraph._element = None


def show_load_error_msgbox(errors):
    msgbox = QMessageBox()
    msgbox.setText("Errors occurred while loading report template:")
    msgbox.setInformativeText("\n".join(errors))
    msgbox.exec()
