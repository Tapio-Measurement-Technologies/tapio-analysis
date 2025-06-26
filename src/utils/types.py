from dataclasses import dataclass, field
from typing import Optional, Callable, Literal, Protocol, ClassVar
from abc import abstractmethod
from PyQt6.QtWidgets import QPushButton
from utils.measurement import Measurement
import json

AnalysisType = Literal["MD", "CD"]
ModuleName = str

@dataclass
class PlotAnnotation:
    text: str
    xy: tuple[float, float]
    xytext: Optional[tuple[float, float]] = None
    arrowprops: Optional[dict] = field(default_factory=dict)
    style: Optional[dict] = field(default_factory=dict)
    axes_index: Optional[int] = None

    @staticmethod
    def from_dict(data: dict) -> "PlotAnnotation":
        return PlotAnnotation(**data)

@dataclass
class PreconfiguredAnalysis:
    analysis_name: str
    analysis_type: AnalysisType
    attributes: dict
    annotations: list[PlotAnnotation]

    def to_json(self) -> str:
        return json.dumps(self, default=lambda o: o.__dict__, indent=4)

@dataclass
class MainWindowSectionModule:
    """
    Module to be added to a main window section

    Arguments:
        module_name: str - The name of the module to load
        analysis_name: Optional[str] - Optional, overrides the analysis name from the module (used e.g. in button titles)
        type: Optional[AnalysisType] - The type of analysis to load
        callback: Optional[Callable] - Optional, overrides callback to be called when the button is pressed
        arguments: Optional[dict] - Optional, arguments to pass to the callback or callback_name method
        callback_name: Optional[str] - Optional, name of a method in the MainWindow class to be called when
                      the button is pressed. This allows referencing MainWindow methods without creating
                      circular imports. The method will be called with the arguments specified in the arguments field.
    """
    module_name: str
    analysis_name: Optional[str] = None
    type: Optional[AnalysisType] = None
    callback: Optional[Callable] = None
    arguments: dict = field(default_factory=dict)
    callback_name: Optional[str] = None
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

class LoaderModule(Protocol):
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

class ExporterModule(Protocol):
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
