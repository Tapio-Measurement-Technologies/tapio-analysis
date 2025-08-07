from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QMenuBar, QVBoxLayout, QFileDialog
from PyQt6.QtGui import QAction
from typing import Type, List, Optional, TypeVar, Generic, Any
from dataclasses import dataclass
from gui.components import PlotMixin
from utils.measurement import Measurement
from utils.types import PlotAnnotation, AnalysisType, PreconfiguredAnalysis
import settings
import json
from utils import store
import numpy as np

class AnalysisControllerBase(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__()
        self.analysis_name = self.__module__
        self.measurement: Measurement = measurement
        self.window_type: AnalysisType = window_type
        self.analysis_type: AnalysisType = window_type # For backwards compatibility
        self.show_annotations: bool = True # TODO: Add mixin checkboxes (if necessary)
        self.channel: str = measurement.channels[0]
        self.fs = 1 / measurement.sample_step
        self.distances = (
            measurement.cd_distances if self.window_type == "CD"
            else measurement.distances
        )
        self.max_dist = np.max(self.distances)
        self.max_freq = self.fs / 2

        if attributes:
            self.set_attributes(attributes)

        if annotations:
            self.set_annotations(annotations)

    def set_default(self, key: str, value: Any):
        if not hasattr(self, key):
            setattr(self, key, value)

    def set_attributes(self, attributes: dict):
        for key, value in attributes.items():
            setattr(self, key, value)

    def set_annotations(self, annotations: list[PlotAnnotation]):
        for annotation in annotations:
            self.canvas.add_annotation(annotation)
        self.show_annotations = len(annotations) > 0

    def export_attributes(self) -> dict:
        return {
            key: getattr(self, key)
            for key in settings.ANALYSIS_EXPORT_ATTRIBUTES
            if hasattr(self, key)
        }

    def export_analysis(self) -> PreconfiguredAnalysis:
        return PreconfiguredAnalysis(
            analysis_name=self.analysis_name,
            analysis_type=self.analysis_type,
            attributes=self.export_attributes(),
            annotations=self.canvas.get_annotations()
        )

ControllerT = TypeVar("ControllerT", bound=AnalysisControllerBase)
class AnalysisWindowBase(QWidget, Generic[ControllerT]):
    closed = pyqtSignal()

    def __init__(self, controller: ControllerT, window_type: AnalysisType):
        super().__init__()
        self.controller: ControllerT = controller
        self.analysis_name = self.controller.analysis_name
        self.measurement: Measurement = self.controller.measurement
        self.window_type: AnalysisType = window_type
        self.analysis_type: AnalysisType = window_type # For backwards compatibility

        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.menu_bar = QMenuBar()
        self.main_layout.setMenuBar(self.menu_bar)

        self.file_menu = self.menu_bar.addMenu('File')
        self.save_analysis_action = QAction('Save analysis', self)
        self.save_analysis_action.triggered.connect(self.on_save_analysis)
        self.file_menu.addAction(self.save_analysis_action)

    def on_save_analysis(self):
        dialog = QFileDialog()
        options = QFileDialog.options(dialog)
        fileName, _ = QFileDialog.getSaveFileName(self, "Save analysis as...", "", "JSON Files (*.json)", options=options)
        if fileName:
            if not fileName.endswith('.json'):
                fileName += '.json'
            with open(fileName, 'w') as f:
                f.write(self.controller.export_analysis().to_json())

    def bring_to_front(self):
        self.raise_()
        self.setWindowState(
            self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

class Analysis:
    controller: AnalysisControllerBase
    window: AnalysisWindowBase
    analysis_name: str
    window_type: AnalysisType
    measurement: Measurement

    def __init__(self,
                 measurement: Measurement,
                 analysis_name: str,
                 window_type: AnalysisType,
                 annotations: list[PlotAnnotation] = [],
                 attributes: dict = {},
                 open_window: bool = True
    ):
        self.analysis_name = analysis_name
        self.window_type = window_type
        self.measurement = measurement

        analysis_module = store.analyses[analysis_name] # Throws KeyError if analysis_name is not found
        self.controller = analysis_module.AnalysisController(measurement, window_type, annotations, attributes)
        self.window = analysis_module.AnalysisWindow(self.controller, window_type)

        if open_window:
            self.window.show()

    def export(self) -> PreconfiguredAnalysis:
        return self.controller.export_analysis()

@dataclass
class AnalysisModule:
    """Protocol defining the interface for analysis modules"""
    analysis_name: str
    analysis_types: List[AnalysisType]
    AnalysisController: Type[AnalysisControllerBase]
    AnalysisWindow: Type[AnalysisWindowBase]
    allow_multiple_instances: Optional[bool] = True # Flag to control if multiple windows of this analysis can be opened

def parse_preconfigured_analyses(data: str) -> list[PreconfiguredAnalysis]:
    try:
        json_data = json.loads(data)
        if not isinstance(json_data, list):
            json_data = [json_data]

        analyses = []
        for item in json_data:
            if isinstance(item, str):
                item = json.loads(item)

            # Convert annotation dicts to PlotAnnotation objects
            if 'annotations' in item and item['annotations']:
                item['annotations'] = [PlotAnnotation.from_dict(ann) for ann in item['annotations']]

            analyses.append(PreconfiguredAnalysis(**item))
        return analyses
    except Exception as e:
        print(f"Error parsing preconfigured analyses: {e}")
        return []