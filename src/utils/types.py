from dataclasses import dataclass, field
from typing import Optional, Callable, Literal, Protocol, ClassVar, List, Type
from abc import abstractmethod
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QObject
from utils.measurement import Measurement

AnalysisType = Literal["MD", "CD"]
ModuleName = str

@dataclass
class MainWindowSectionModule:
    """
    Module to be added to a main window section

    Arguments:
        name: str - The name of the module to load
        type: Optional[AnalysisType] - The type of analysis to load
        callback: Optional[Callable] - Optional, overrides callback to be called when the button is pressed
        arguments: Optional[dict] - Optional, overrides the section arguments
    """
    name: str
    type: Optional[AnalysisType] = None
    callback: Optional[Callable] = None
    arguments: dict = field(default_factory=dict)
    button: Optional[QPushButton] = None

    def __post_init__(self):
        if self.type:
            self.arguments.update({"window_type": self.type})

@dataclass
class MainWindowSection:
    """
    Section to be added to the main window

    Arguments:
        name: str - The name of the section
        modules: list[MainWindowSectionModule] - The modules to be added to the section
    """
    name: str
    modules: list[MainWindowSectionModule]

class Loader(Protocol):
    """Protocol defining the interface for loader modules."""

    menu_text: ClassVar[str]
    file_types: ClassVar[str]

    @staticmethod
    @abstractmethod
    def load_data(fileNames: list[str]) -> Measurement | None:
        """
        Load data from the specified files.

        Args:
            fileNames: List of file paths to load data from
        """
        pass

class Exporter(Protocol):
    """Protocol defining the interface for exporter modules."""

    menu_text: ClassVar[str]
    file_types: ClassVar[str]

    @staticmethod
    @abstractmethod
    def export_data(fileName: str) -> None:
        """
        Export data to the specified file.

        Args:
            fileName: Path to the file where data should be exported
        """
        pass

class AnalysisController(Protocol):
    """Protocol defining the interface for analysis controllers"""
    measurement: Measurement
    updated: QObject  # This will be a pyqtSignal in implementations

    def __init__(self, measurement: Measurement, window_type: AnalysisType = "MD") -> None: ...
    def plot(self): ...
    def getStatsTableData(self): ...
    def getExportData(self): ...

class AnalysisWindow(Protocol):
    """Protocol defining the interface for analysis windows

    When both measurement and controller arguments are supplied during initialization,
    the measurement argument is ignored since the controller already contains a reference
    to the measurement.
    """
    controller: AnalysisController
    measurement: Measurement

    def __init__(self,
                 window_type: AnalysisType = "MD",
                 controller: Optional[AnalysisController] = None,
                 measurement: Optional[Measurement] = None) -> None: ...
    def refresh(self) -> None: ...

class AnalysisModule(Protocol):
    """Protocol defining the interface for analysis modules"""
    analysis_name: str
    analysis_types: List[AnalysisType]
    AnalysisController: Type[AnalysisController]
    AnalysisWindow: Type[AnalysisWindow]
