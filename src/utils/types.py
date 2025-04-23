from enum import Enum


class MeasurementFileType(Enum):
    HEADER = "Header"
    CALIBRATION = "Calibration"
    DATA = "Data"
    PM = "Paper machine"
    SAMPLES = "CD Sample locations"

class AnalysisType(Enum):
    CD = "CD"
    MD = "MD"
