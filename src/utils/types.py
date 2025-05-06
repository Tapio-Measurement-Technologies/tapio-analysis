from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Literal
from PyQt6.QtWidgets import QPushButton

AnalysisType = Literal["MD", "CD"]

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

class MeasurementFileType(Enum):
    HEADER = "Header"
    CALIBRATION = "Calibration"
    DATA = "Data"
    PM = "Paper machine"
    SAMPLES = "CD Sample locations"

