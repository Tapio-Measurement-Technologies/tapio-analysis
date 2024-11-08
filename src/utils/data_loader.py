import numpy as np
import pandas as pd
import logging
from utils.tapio_legacy_parser import load_legacy_data
import json
import settings

import traceback

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

    def load_cd_samples_data(self):
        with open(self.samples_file_path, 'r') as f:
            cd_data = json.load(f)
            self.peak_channel = cd_data['peak_channel']
            self.threshold = cd_data['threshold']
            self.peak_locations = cd_data['peak_locations']
            self.selected_samples = cd_data['selected_samples']
        self.split_data_to_segments()

    def load_legacy_data(self):
        sensor_df, units, sample_step, info, pm_speed = load_legacy_data(self.header_file_path,
                                                                         self.calibration_file_path,
                                                                         self.data_file_path)

        sensor_df = sensor_df.drop(columns=settings.IGNORE_CHANNELS, errors='ignore')

        # TODO: Implement here the logic in settings.CALCULATED_CHANNELS


        for channel in settings.CALCULATED_CHANNELS:
            name = channel['name']
            unit = channel['unit']
            function = channel['function']
            try:
                sensor_df[name] = function(sensor_df)
                units[name] = unit
                print(f"Added calculated channel {name}")
            except Exception as e:
                print(f"Failed to calculate channel {name}: {e}")
                traceback.print_exc()




        self.measurement_label = info
        self.channels = sensor_df.columns
        self.channel_df = sensor_df
        self.units = units
        self.sample_step = sample_step
        self.pm_speed = pm_speed

        number_of_measurements = len(sensor_df)
        indices = np.arange(number_of_measurements)
        self.distances = indices * sample_step
        logging.info("Loaded data")


    def split_data_to_segments(self):
        self.segments = {}
        tape_width_m = settings.TAPE_WIDTH_MM / 1000.0

        for channel in self.channels:
            segments = []
            for i in range(len(self.peak_locations)-1):
                start_dist = self.peak_locations[i] + tape_width_m
                end_dist = self.peak_locations[i+1] - tape_width_m

                start_index = np.searchsorted(
                    self.distances, start_dist, side='left')
                end_index = np.searchsorted(
                    self.distances, end_dist, side='right')

                segment = self.channel_df[channel].iloc[start_index:end_index]
                segments.append(segment)

            min_length = min(map(len, segments))
            trimmed_segments = [
                seg[(len(seg) - min_length) // 2: (len(seg) + min_length) // 2] for seg in segments]

            self.segments[channel] = np.array(trimmed_segments)

        indices = np.arange(min_length)
        self.cd_distances = indices * self.sample_step
