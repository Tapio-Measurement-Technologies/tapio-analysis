from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget
from typing import Type, Protocol, List, Optional, TypeVar, Generic
from dataclasses import dataclass
from gui.components import PlotMixin
from utils.measurement import Measurement
from utils.types import PlotAnnotation, AnalysisType

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

def make_analysis_class(controller_cls: Type[AnalysisControllerBase], window_cls: Type[AnalysisWindowBase]):
    class Analysis:
        def __init__(self,
                     measurement: Measurement,
                     window_type: AnalysisType,
                     annotations: list[PlotAnnotation] = [],
                     attributes: dict = {},
                     open_window: bool = True
        ):
            self.controller = controller_cls(measurement, window_type, annotations, attributes)
            self.window = window_cls(self.controller, window_type)

            if open_window:
                self.window.show()

    return Analysis

class Analysis(Protocol):
    controller: AnalysisControllerBase
    window: AnalysisWindowBase

@dataclass
class AnalysisModule:
    """Protocol defining the interface for analysis modules"""
    analysis_name: str
    analysis_types: List[AnalysisType]
    AnalysisController: Type[AnalysisControllerBase]
    AnalysisWindow: Type[AnalysisWindowBase]
    allow_multiple_instances: Optional[bool] = True # Flag to control if multiple windows of this analysis can be opened

    def __post_init__(self):
        self.Analysis = make_analysis_class(self.AnalysisController, self.AnalysisWindow)