from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget
from typing import Type, List, Optional, TypeVar, Generic
from dataclasses import dataclass
from gui.components import PlotMixin
from utils.measurement import Measurement
from utils.types import PlotAnnotation, AnalysisType
from utils import store

class AnalysisControllerBase(QObject, PlotMixin):
    updated = pyqtSignal()

    def __init__(self, measurement: Measurement, window_type: AnalysisType, annotations: list[PlotAnnotation] = [], attributes: dict = {}):
        super().__init__()
        self.measurement: Measurement = measurement
        self.window_type: AnalysisType = window_type
        self.annotations: list[PlotAnnotation] = annotations
        self.show_annotations: bool = len(annotations) > 0
        self.channel: str = measurement.channels[0]

        for key, value in attributes.items():
            setattr(self, key, value)

ControllerT = TypeVar("ControllerT", bound=AnalysisControllerBase)
class AnalysisWindowBase(QWidget, Generic[ControllerT]):
    closed = pyqtSignal()

    def __init__(self, controller: ControllerT, window_type: AnalysisType):
        super().__init__()
        self.controller: ControllerT = controller
        self.measurement: Measurement = self.controller.measurement
        self.window_type: AnalysisType = window_type

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
