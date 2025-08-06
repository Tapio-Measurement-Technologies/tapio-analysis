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

@dataclass(frozen=True)
class DataSegment:
    start_dist: float
    end_dist: float
    sample_step: float

    @property
    def start_index(self):
        return int(self.start_dist / self.sample_step)

    @property
    def end_index(self):
        return int(self.end_dist / self.sample_step)

    @property
    def length(self):
        return self.end_dist - self.start_dist

# TODO: Handle tape width in CDSegment
CDSegment = DataSegment
PatchSegment = DataSegment

@dataclass(frozen=True)
class MeasurementChannel:
    name: str
    unit: str
    data: pd.DataFrame

    def get_segment(self, start_index: int, end_index: int) -> pd.DataFrame:
        return self.data.iloc[start_index:end_index]

    def get_segment(self, segment: CDSegment) -> pd.DataFrame:
        return self.get_segment(segment.start_index, segment.end_index)

    def patch(self, segments: list[PatchSegment]) -> pd.DataFrame:
        patched_data = self.data.copy()
        for segment in segments:
            # TODO: Patch data with average noise data
            patched_data.iloc[segment.start_index:segment.end_index] = np.nan
        return patched_data

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
    # cd_segments: list[CDSegment] = field(default_factory=list)
    patch_segments: list[PatchSegment] = field(default_factory=list)

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

    # def get_cd_segments(self, peak_locations: list[float], tape_width_m: float) -> list[CDSegment]:
    #     segments = []
    #     for i in range(len(peak_locations)-1):
    #         start_dist = peak_locations[i] + tape_width_m
    #         end_dist = peak_locations[i+1] - tape_width_m
    #         segments.append(CDSegment(start_dist, end_dist, self.sample_step))
    #     return segments

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
        # self.cd_segments = self.get_cd_segments(self.peak_locations, tape_width_m)

        if segments:
            # Only calculate cd_distances if we have segments
            min_length = min(len(segments[channel][0]) for channel in segments)
            indices = np.arange(min_length)
            self.cd_distances = indices * self.sample_step

        # if self.cd_segments:
        #     min_length = min(segment.length for segment in self.cd_segments)
        #     indices = np.arange(min_length)
        #     self.cd_distances = indices * self.sample_step
        #     print("CD distances from split_data_to_segments:")
        #     print(self.cd_distances)
        #     print(len(self.cd_distances))

        return self