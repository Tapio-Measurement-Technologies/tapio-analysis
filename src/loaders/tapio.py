from utils.data_loader import DataMixin
import os

menu_text = "Load Tapio data"
menu_priority = 1

dataMixin = DataMixin.getInstance()
file_types = "All Files (*);;Calibration files (*.ca2);;Data files (*.da2);;Header files (*.pk2);;Paper machine files (*.pmdata.json);;CD Sample location files (*.samples.json)"


def load_data(fileNames: list[str]):

    for fn in fileNames:
        # Extract the base name of the file
        basename = os.path.basename(fn)

        if fn.lower().endswith('.ca2'):
            dataMixin.calibration_file_path = fn
        elif fn.lower().endswith('.da2'):
            dataMixin.data_file_path = fn
        elif fn.lower().endswith('.pk2'):
            dataMixin.header_file_path = fn
        elif fn.lower().endswith('.pmdata.json'):
            dataMixin.pm_file_path = fn
            dataMixin.load_pm_file()
        elif fn.lower().endswith('.samples.json'):
            dataMixin.samples_file_path = fn

    if (dataMixin.calibration_file_path and dataMixin.data_file_path and dataMixin.header_file_path):
        dataMixin.load_legacy_data()

        if (dataMixin.samples_file_path):
            dataMixin.load_cd_samples_data()
            dataMixin.split_data_to_segments()
