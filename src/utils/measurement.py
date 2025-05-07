from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
import settings
import json
from enum import Enum

class MeasurementFileType(Enum):
    HEADER = "Header"
    CALIBRATION = "Calibration"
    DATA = "Data"
    PM = "Paper machine"
    SAMPLES = "CD Sample locations"

@dataclass
class Measurement:
    channel_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    channels: list[str] = field(default_factory=list)
    units: list[str] = field(default_factory=list)
    distances: list[float] = field(default_factory=list)
    header_file_path: Optional[str] = None
    calibration_file_path: Optional[str] = None
    data_file_path: Optional[str] = None
    pm_file_path: Optional[str] = None
    measurement_label: Optional[str] = None
    samples_file_path: Optional[str] = None
    peak_channel: Optional[str] = None
    threshold: Optional[float] = None
    sample_step: Optional[float] = None
    pm_speed: Optional[float] = None
    peak_locations: list[float] = field(default_factory=list)
    selected_samples: list[int] = field(default_factory=list)
    segments: dict[str, list[float]] = field(default_factory=dict)
    cd_distances: list[float] = field(default_factory=list)
    pm_data: dict[str, pd.DataFrame] = field(default_factory=dict)

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

    def load_pm_file(self):
        with open(self.pm_file_path, 'r') as f:
            self.pm_data = json.load(f)

    def split_data_to_segments(self):
        """Split data into segments based on peak locations."""
        segments = {}
        tape_width_m = settings.TAPE_WIDTH_MM / 1000.0

        for channel in self.channels:
            channel_segments = []
            for i in range(len(self.peak_locations)-1):
                start_dist = self.peak_locations[i] + tape_width_m
                end_dist = self.peak_locations[i+1] - tape_width_m

                start_index = np.searchsorted(
                    self.distances, start_dist, side='left')
                end_index = np.searchsorted(
                    self.distances, end_dist, side='right')

                segment = self.channel_df[channel].iloc[start_index:end_index]
                channel_segments.append(segment)

            if channel_segments:
                min_length = min(map(len, channel_segments))
                trimmed_segments = [
                    seg[(len(seg) - min_length) // 2: (len(seg) + min_length) // 2] for seg in channel_segments]

                segments[channel] = np.array(trimmed_segments)

        self.segments = segments

        if segments:
            # Only calculate cd_distances if we have segments
            min_length = min(len(segments[channel][0]) for channel in segments)
            indices = np.arange(min_length)
            self.cd_distances = indices * self.sample_step

        return self