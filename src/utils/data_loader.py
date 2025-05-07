import pandas as pd
import json
from utils.types import MeasurementFileType

class DataMixin:
    _instance = None

    def __init__(self):
        super().__init__()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataMixin, cls).__new__(cls)
            cls._instance.init_attributes()  # Initial setup
        return cls._instance

    def init_attributes(self):
        # Initialize or reset all instance attributes here
        self.channel_df = pd.DataFrame()
        self.channels = []
        self.units = []
        self.distances = []
        self.header_file_path = None
        self.calibration_file_path = None
        self.data_file_path = None
        self.pm_file_path = None
        self.measurement_label = None
        self.samples_file_path = None
        self.peak_channel = None
        self.threshold = None
        self.peak_locations = []
        self.selected_samples = []
        self.segments = []

    @classmethod
    def reset(cls):
        if cls._instance:
            cls._instance.init_attributes()

    @classmethod
    def getInstance(cls):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            # Initialize any attributes of the singleton here
        return cls._instance

    def updateData(self):
        # Implement the logic to update data here
        pass

    def printData(self):
        # Implement the logic to print data here
        pass

    def load_pm_file(self):
        with open(self.pm_file_path, 'r') as f:
            self.pm_data = json.load(f)

    def get_file_path(self, file_type: MeasurementFileType):
        if file_type == MeasurementFileType.HEADER:
            return self.header_file_path
        elif file_type == MeasurementFileType.CALIBRATION:
            return self.calibration_file_path
        elif file_type == MeasurementFileType.DATA:
            return self.data_file_path
        elif file_type == MeasurementFileType.PM:
            return self.pm_file_path
        elif file_type == MeasurementFileType.SAMPLES:
            return self.samples_file_path
