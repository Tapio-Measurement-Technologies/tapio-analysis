import logging
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
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

    def get_segment(self, start_index_or_segment, end_index: Optional[int] = None) -> pd.DataFrame:
        if end_index is None:
            segment = start_index_or_segment
            start_index = segment.start_index
            end_index = segment.end_index
        else:
            start_index = start_index_or_segment

        return self.data.iloc[start_index:end_index]

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
    tape_width_mm: float = field(
        default_factory=lambda: get_default_tape_width_mm()
    )
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

    # def get_cd_segments(self, peak_locations: list[float], tape_half_width_m: float) -> list[CDSegment]:
    #     segments = []
    #     for i in range(len(peak_locations)-1):
    #         start_dist = peak_locations[i] + tape_half_width_m
    #         end_dist = peak_locations[i+1] - tape_half_width_m
    #         segments.append(CDSegment(start_dist, end_dist, self.sample_step))
    #     return segments

    def split_data_to_segments(self):
        """Split data into segments based on peak locations."""
        segments = {}
        tape_half_width_m = self.tape_width_mm / 2000.0

        for channel in self.channels:
            channel_segments = []
            for i in range(len(self.peak_locations)-1):
                start_dist = self.peak_locations[i] + tape_half_width_m
                end_dist = self.peak_locations[i+1] - tape_half_width_m

                start_index = np.searchsorted(
                    self.distances, start_dist, side='left')
                end_index = np.searchsorted(
                    self.distances, end_dist, side='right')

                segment = self.channel_df[channel].iloc[start_index:end_index]
                channel_segments.append(segment)

            if channel_segments:
                min_length = min(map(len, channel_segments))
                trimmed_segments = [
                    trim_segment(segment, min_length) for segment in channel_segments]

                segments[channel] = np.array(trimmed_segments)

        self.segments = segments
        # self.cd_segments = self.get_cd_segments(self.peak_locations, tape_half_width_m)

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


def drop_unusable_channels(channel_df, units=None):
    """Remove channels that carry no usable data.

    A sensor that was disconnected, or whose calibration produced no finite
    values, yields an all-NaN column. Such a channel cannot be plotted or
    correlated and only clutters the channel selectors, so it is dropped at load
    time. DROP_CHANNEL_NAN_FRACTION sets how much of a channel must be
    non-finite before it is discarded; at the default of 1.0 only entirely
    non-finite channels go.

    :param channel_df: DataFrame of channel data.
    :param units: Optional unit mapping, pruned alongside the columns.
    :return: (channel_df, units) with unusable channels removed.
    """
    try:
        import settings
        threshold = getattr(settings, "DROP_CHANNEL_NAN_FRACTION", 1.0)
    except ImportError:
        threshold = 1.0

    if channel_df is None or channel_df.empty or threshold is None:
        return channel_df, units

    dropped = []
    for channel in channel_df.columns:
        values = channel_df[channel].to_numpy(dtype=float, na_value=np.nan)
        if len(values) == 0:
            continue
        non_finite_fraction = np.count_nonzero(~np.isfinite(values)) / len(values)
        if non_finite_fraction >= threshold:
            dropped.append((channel, non_finite_fraction))

    if not dropped:
        return channel_df, units

    for channel, fraction in dropped:
        logging.warning(
            "Ignoring channel %s: %.0f%% of its samples are not finite.",
            channel, 100 * fraction)

    channel_df = channel_df.drop(columns=[channel for channel, _ in dropped])

    if isinstance(units, dict):
        for channel, _ in dropped:
            units.pop(channel, None)

    return channel_df, units


def get_cd_segment_alignment():
    try:
        import settings
        return getattr(settings, "CD_SEGMENT_ALIGNMENT", "left")
    except ImportError:
        return "left"


def trim_segment(segment, length):
    """Trim a CD strip to a common length, honouring CD_SEGMENT_ALIGNMENT.

    Strips differ slightly in length because tape spacing varies, so they must
    be cut to a common length before they can be averaged. Which end is kept
    decides what CD position index 0 of every profile refers to:

      "left"   keep the start, so every profile begins at its leading tape.
      "right"  keep the end, so every profile ends at its trailing tape.
      "center" cut equally from both ends. This shifts each strip by half its
               own length difference relative to the others, which smears short
               wavelength CD structure in the mean profile and spectrum.

    :param segment: One CD strip.
    :param length: Common length in samples.
    :return: The trimmed strip.
    """
    alignment = get_cd_segment_alignment()
    extra = len(segment) - length

    if extra <= 0:
        return segment

    if alignment == "right":
        return segment[extra:]
    if alignment == "center":
        start = extra // 2
        return segment[start:start + length]
    if alignment != "left":
        logging.warning(
            "Unknown CD_SEGMENT_ALIGNMENT %r, using 'left'. "
            "Valid values are 'left', 'center' and 'right'.", alignment)

    return segment[:length]


def get_default_tape_width_mm():
    try:
        import settings
        return getattr(settings, "TAPE_WIDTH_MM", 50.0)
    except ImportError:
        return 50.0
