from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QMenuBar, QVBoxLayout
from typing import Type, List, Optional, TypeVar, Generic
from dataclasses import dataclass
from gui.components import PlotMixin
from utils.measurement import Measurement
from utils.types import PlotAnnotation, AnalysisType, PreconfiguredAnalysis
import settings
import json
from utils import store

class AnalysisControllerBase(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__()
        self.analysis_name = self.__module__
        self.measurement: Measurement = measurement
        self.window_type: AnalysisType = window_type
        self.analysis_type: AnalysisType = window_type # For backwards compatibility
        self.show_annotations: bool = len(annotations) > 0 # TODO: Add mixin checkboxes (if necessary)
        self.channel: str = measurement.channels[0]

        if attributes:
            self.set_attributes(attributes)

        if annotations:
            self.set_annotations(annotations)

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

@dataclass
class AnalysisModule:
    """Protocol defining the interface for analysis modules"""
    analysis_name: str
    analysis_types: List[AnalysisType]
    AnalysisController: Type[AnalysisControllerBase]
    AnalysisWindow: Type[AnalysisWindowBase]
    allow_multiple_instances: Optional[bool] = True # Flag to control if multiple windows of this analysis can be opened
