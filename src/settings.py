import os

import importlib.util
import sys
from utils.types import MainWindowSection, MainWindowSectionModule

DEBUG = False

# Meters per minute
PAPER_MACHINE_SPEED_DEFAULT = 1600.00
FILTER_NUMTAPS = 2500

REPORT_ADDITIONAL_INFO_DEFAULT = f"Speed at reel: {PAPER_MACHINE_SPEED_DEFAULT:.0f} m/min\nGrammage:"
MD_REPORT_TEMPLATE_DEFAULT = None
CD_REPORT_TEMPLATE_DEFAULT = None

REPORT_FORMAT_DEFAULT = 'latex'

FORCE_PRIMARY_SCALE_SUPPLEMENTARY = False

LOADERS_DIR = 'loaders'
EXPORTERS_DIR = 'exporters'
ANALYSIS_DIR = 'analyses'
ANALYSIS_SECTIONS = [
    MainWindowSection(
        name="MD Analysis",
        modules=[
            MainWindowSectionModule(module_name="time_domain",         type="MD"),
            MainWindowSectionModule(module_name="spectrum",            type="MD"),
            MainWindowSectionModule(module_name="spectrogram",         type="MD"),
            MainWindowSectionModule(module_name="channel_correlation", type="MD"),
            MainWindowSectionModule(module_name="correlation_matrix",  type="MD"),
            MainWindowSectionModule(module_name="formation",           type="MD"),
            MainWindowSectionModule(module_name="coherence",           type="MD"),
            # MainWindowSectionModule(module_name="cepstrum",            type="MD")
        ]
    ),
    MainWindowSection(
        name="CD Analysis",
        modules=[
            MainWindowSectionModule(module_name="find_samples"),
            MainWindowSectionModule(module_name="cd_profile",           type="CD"),
            MainWindowSectionModule(module_name="cd_profile_waterfall", type="CD"),
            MainWindowSectionModule(module_name="spectrum",             type="CD"),
            MainWindowSectionModule(module_name="spectrogram",          type="CD"),
            MainWindowSectionModule(module_name="channel_correlation",  type="CD"),
            MainWindowSectionModule(module_name="correlation_matrix",   type="CD"),
            MainWindowSectionModule(module_name="vca",                  type="CD"),
            MainWindowSectionModule(module_name="formation",            type="CD"),
            MainWindowSectionModule(module_name="coherence",            type="CD"),
            # MainWindowSectionModule(module_name="cepstrum",             type="CD")
        ]
    ),
    MainWindowSection(
        name="Reports",
        modules=[
            MainWindowSectionModule(module_name="report", analysis_name="MD Report", type="MD", callback_name="openReport"),
            MainWindowSectionModule(module_name="report", analysis_name="CD Report", type="CD", callback_name="openReport")
        ]
    )
]
ANALYSES_EXCLUDED_FROM_REPORT = ["sos", "find_samples"]

UPDATE_ON_SLIDE = False
IGNORE_CHANNELS = ["Density"]
CORRELATION_MATRIX_SAMPLE_LIMIT = 2000
CORRELATION_MATRIX_HISTOGRAM_BINS = 20
CORRELATION_MATRIX_LABEL_FONT_SIZE = 8
CORRELATION_MATRIX_WINDOW_SIZE = (1000, 600)


# Formation analysis settings
FORMATION_TRANSMISSION_CHANNEL = "Transmission"
FORMATION_BW_CHANNEL = "BW"
FORMATION_WINDOW_LENGTH = 400
FORMATION_WINDOW_SIZE = (1000, 600)

SPECTROGRAM_COLORMAP = "viridis"

MAX_HARMONICS_DISPLAY = 10
MAX_HARMONICS_FREQUENCY_ESTIMATOR = 1

# CD Find samples settings
CD_SAMPLE_LENGTH_SLIDER_MIN = 2  # Minimum allowed sample length in meters
CD_SAMPLE_LENGTH_SLIDER_MAX = 15  # Maximum allowed sample length in meters
CD_SAMPLE_LENGTH_SLIDER_STEP = 0.01

# Tape width which will be cut off from all CD samples
TAPE_WIDTH_MM = 50.00
# Minimum length of CD Sample the software will detect
CD_SAMPLE_MIN_LENGTH_M = 4.00
CD_SAMPLE_MAX_LENGTH_M = 12.00


# Number of decimals in the analysis range slider
ANALYSIS_RANGE_DECIMALS = 2
BAND_PASS_FILTER_DECIMALS = 2
BAND_PASS_FILTER_SINGLESTEP = 0.01


# Time domain default values
TIME_DOMAIN_TITLE_SHOW = True
TIME_DOMAIN_WINDOW_SIZE = (1200, 500)
TIME_DOMAIN_FIXED_YLIM_ALL_DATA = False
TIME_DOMAIN_MINOR_GRID = True


TIME_DOMAIN_FIXED_XTICKS = None


TIME_DOMAIN_BAND_PASS_LOW_DEFAULT_1M = 0.00
TIME_DOMAIN_BAND_PASS_HIGH_DEFAULT_1M = 30.00

TIME_DOMAIN_ANALYSIS_RANGE_LOW_DEFAULT = 0.00
TIME_DOMAIN_ANALYSIS_RANGE_HIGH_DEFAULT = 0.10

TIME_DOMAIN_SHOW_UNFILTERED_DATA_DEFAULT = False
TIME_DOMAIN_SHOW_TIME_LABELS_DEFAULT = False


TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER = 1
TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT = "m"


SPECTRUM_WINDOW_SIZE = (1200, 600)
SPECTRUM_WELCH_WINDOW = "hann"
SPECTRUM_AMPLITUDE_SCALING = 1  # Set to 2 for peak-to-peak, 1/sqrt(2) for RMS
SPECTRUM_SHOW_LEGEND = True
SPECTRUM_LEGEND_OUTSIDE_PLOT = False
SPECTRUM_MINOR_GRID = True


# MD (Machine Direction) Spectrum Analysis Settings
MD_SPECTRUM_DEFAULT_LENGTH = 20000
MD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT = 0.00
MD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT = 0.5

# This is in units 1/m
MD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT = 0.00
MD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT = 500.00

MD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT = 0.00
MD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT = 1.00
MD_SPECTRUM_OVERLAP = 0.85
MD_SPECTRUM_FIXED_YLIM = {}

# MD_SPECTRUM_FIXED_YLIM = {"Tapio BW": (0, 0.2)}


SPECTROGRAM_WINDOW_SIZE = (1200, 600)


MD_SPECTRUM_LENGTH_SLIDER_MIN = 1000
MD_SPECTRUM_LENGTH_SLIDER_MAX = 100000
MD_SPECTROGRAM_OVERLAP = 0.75

MD_SPECTROGRAM_DEFAULT_LENGTH = 5000
MD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT = 0.0
MD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT = 0.5
MD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT = 0
MD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT = 1
MD_SPECTROGRAM_OVERLAP = 0.75

MD_SPECTROGRAM_LENGTH_SLIDER_MIN = 1000
MD_SPECTROGRAM_LENGTH_SLIDER_MAX = 100000
MD_SPECTROGRAM_OVERLAP = 0.75

# CD (Cross Direction) Spectrum Analysis Settings
CD_SPECTRUM_DEFAULT_LENGTH = 5000
CD_SPECTRUM_FREQUENCY_RANGE_MIN_DEFAULT = 0.0
CD_SPECTRUM_FREQUENCY_RANGE_MAX_DEFAULT = 0.5

# This is in units 1/m
CD_SPECTRUM_PEAK_RANGE_MIN_DEFAULT = 0
CD_SPECTRUM_PEAK_RANGE_MAX_DEFAULT = 500

CD_SPECTRUM_ANALYSIS_RANGE_LOW_DEFAULT = 0
CD_SPECTRUM_ANALYSIS_RANGE_HIGH_DEFAULT = 1
CD_SPECTRUM_OVERLAP = 0.85
CD_SPECTRUM_FIXED_YLIM = {}

# fraction of points by which consecutive segments overlap

CD_SPECTRUM_LENGTH_SLIDER_MIN = 1000
CD_SPECTRUM_LENGTH_SLIDER_MAX = 10000

# CD (Cross Direction) Spectrum Analysis Settings
CD_SPECTROGRAM_DEFAULT_LENGTH = 500
CD_SPECTROGRAM_FREQUENCY_RANGE_MIN_DEFAULT = 0.0
CD_SPECTROGRAM_FREQUENCY_RANGE_MAX_DEFAULT = 0.3
CD_SPECTROGRAM_ANALYSIS_RANGE_LOW_DEFAULT = 0
CD_SPECTROGRAM_ANALYSIS_RANGE_HIGH_DEFAULT = 1
CD_SPECTROGRAM_OVERLAP = 0.99
# fraction of points by which consecutive segments overlap

CD_SPECTROGRAM_LENGTH_SLIDER_MIN = 100
CD_SPECTROGRAM_LENGTH_SLIDER_MAX = 10000

# MD Correlation matrix settings
MD_CORRELATION_BAND_PASS_LOW_DEFAULT_1M = 0
MD_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M = 30
MD_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT = 0
MD_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT = 1


CORRELATION_ANALYSIS_DISPLAY_UNIT_MULTIPLIER = 1
CORRELATION_ANALYSIS_DISPLAY_UNIT = "m"


# CD Correlation matrix settings
CD_CORRELATION_BAND_PASS_LOW_DEFAULT_1M = 0
CD_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M = 30
CD_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT = 0
CD_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT = 1

EXTRA_DATA_ADJUST_RANGE = 1

# Channel correlation settings
CHANNEL_CORRELATION_SHOW_BEST_FIT = False
CHANNEL_CORRELATION_XCORR_OUTPUT = False

CHANNEL_CORRELATION_WINDOW_SIZE = (1000, 800)


MD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M = 0
MD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M = 30
MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT = 0
MD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT = 0.1

CD_CHANNEL_CORRELATION_BAND_PASS_LOW_DEFAULT_1M = 0
CD_CHANNEL_CORRELATION_BAND_PASS_HIGH_DEFAULT_1M = 30
CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_LOW_DEFAULT = 0
CD_CHANNEL_CORRELATION_ANALYSIS_RANGE_HIGH_DEFAULT = 1

MD_FORMATION_RANGE_LOW_DEFAULT = 0
MD_FORMATION_RANGE_HIGH_DEFAULT = 0.1

FORMATION_TITLE_SHOW = True


CD_FORMATION_RANGE_LOW_DEFAULT = 0
CD_FORMATION_RANGE_HIGH_DEFAULT = 1

# These settings are for MD and CD spectral analysis, how many harmonics to consider in fundamental frequency estimation
NLS_MODEL_ORDER = 1
NLS_STEP = 0.001
NLS_RANGE = 0.1

# CD Profile settings
#THIS will flip loaded data in the parquet loader
FLIP_LOADED_DATA = False

CD_PROFILE_WINDOW_SIZE = (1200, 600)

CD_PROFILE_BAND_PASS_LOW_DEFAULT_1M = 0
CD_PROFILE_BAND_PASS_HIGH_DEFAULT_1M = 30
CD_PROFILE_RANGE_LOW_DEFAULT = 0
CD_PROFILE_RANGE_HIGH_DEFAULT = 1


CD_PROFILE_WATERFALL_OFFSET_DEFAULT = 40
CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS = None
### Example for setting default offsets per channel, if desired
### NOTE: Disables manual adjustment of offsets in the UI
# CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS = {
#     "Caliper": 5,
#     "Transmission": 1,
#     "Basis Weight": 4,
#     "Gloss": 2
# }

CD_PROFILE_CONFIDENCE_INTERVAL = 0.95

CD_PROFILE_DISPLAY_UNIT_MULTIPLIER = 1
CD_PROFILE_DISPLAY_UNIT = "m"
CD_PROFILE_TITLE_SHOW = True
CD_PROFILE_MINOR_GRID = True
CD_PROFILE_MIN_RANGES = {}
# Example: CD_PROFILE_MIN_RANGES = {"Caliper": 4}


# VCA settings
VCA_BAND_PASS_LOW_DEFAULT_1M = 0
VCA_BAND_PASS_HIGH_DEFAULT_1M = 30
VCA_RANGE_LOW_DEFAULT = 0
VCA_RANGE_HIGH_DEFAULT = 1
VCA_COLORMAP = "viridis"
VCA_WINDOW_SIZE = (1100, 700)
VCA_REMOVE_CD_VARIATIONS_DEFAULT = False
VCA_REMOVE_MD_VARIATIONS_DEFAULT = False

# VCA_COLORMAP = "gray"

# Find Samples settings
FIND_SAMPLES_BAND_PASS_LOW_DEFAULT_1M = 0
FIND_SAMPLES_BAND_PASS_HIGH_DEFAULT_1M = 30
FIND_SAMPLES_WINDOW_SIZE = (1000, 800)

CEPSTRUM_WINDOW_SIZE = (1000, 600)
COHERENCE_WINDOW_SIZE = (1000, 600)
SOS_ANALYSIS_WINDOW_SIZE = (800, 600)
PAPER_MACHINE_WINDOW_SIZE = (500, 500)
SAMPLE_SELECT_WINDOW_SIZE = (300, 600)
REPORT_WINDOW_SIZE = (700, 700)

# Waterfall plot settings
WATERFALL_OFFSET_LOW_DEFAULT = 0
WATERFALL_OFFSET_HIGH_DEFAULT = 100

MD_REPORT_SAMPLE_IMAGE_PATH = None
CD_REPORT_SAMPLE_IMAGE_PATH = None
REPORT_LOGO_PATH = None
REPORT_ENABLE_ANALYSIS_TITLE = False


ANALYSIS_EXPORT_ATTRIBUTES = [
    "channel",
    "channel2",
    "band_pass_low",
    "band_pass_high",
    "analysis_range_low",
    "analysis_range_high",
    "peak_detection_range_min",
    "peak_detection_range_max",
    "spectrum_length_slider_min",
    "spectrum_length_slider_max",
    "frequency_range_low",
    "frequency_range_high",
    "selected_samples",
    "selected_elements",
    "selected_freqs",
    "waterfall_offset",
    "confidence_interval",
    "show_profiles",
    "show_min_max",
    "show_legend",
    "show_wavelength",
    "show_unfiltered_data",
    "show_time_labels",
    "remove_md_variations",
    "remove_cd_variations",
    "auto_detect_peaks",
    "nperseg",
    "overlap",
    "machine_speed",
    "min_length",
    "max_length"
]

CD_PROFILE_WATERFALL_COLOR = "tab:blue"


script_dir = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(script_dir, "assets")

CALCULATED_CHANNELS = []

MULTIPLE_SELECT_MODE = False

DOUBLE_SLIDER_FINE_CONTROL_FACTOR = 0.1 # 10% of normal movement
DOUBLE_SLIDER_HANDLE_RADIUS = 4 # px, adjust as needed

SPECTRUM_TITLE_SHOW = True
SPECTRUM_AUTO_DETECT_PEAKS = None
SPECTRUM_LOGARITHMIC_SCALE = False

PLOT_COPY_FORMAT = "png"
PLOT_COPY_DPI = 300

SHOW_WAVELENGTH_DEFAULT = False
AUTO_DETECT_PEAKS_DEFAULT = False

REPORT_GENERATE_PDF = False
REPORT_FORMAT = "word"
# REPORT_FORMAT = "latex" # word or latex

FREQUENCY_SELECTOR_MOUSE_BUTTON = 2

BAND_PASS_FILTER_WAVELENGTH_DECIMALS = 2
STATISTICS_DECIMALS = 2
ANALYSIS_CONTROLS_PANEL_MIN_WIDTH = 300

LOG_WINDOW_SHOW_TIMESTAMPS = True
LOG_WINDOW_MAX_LINES = 1000
CRASH_DIALOG_CONTACT_EMAIL = "info@tapiotechnologies.com"


def get_py_file_vars(py_file_path):
    """
    Returns variables from python file dynamically using importlib.
    """
    if os.path.exists(py_file_path):
        spec = importlib.util.spec_from_file_location("imported_module", py_file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return vars(module)
    return {}

def apply_custom_settings_from_file(py_file_path):
    vars = get_py_file_vars(py_file_path)
    apply_custom_settings_from_dict(vars)

    return vars

def apply_custom_settings_from_dict(settings_dict):
    globals().update(settings_dict)

    print(f"Applied custom settings from provided dictionary:")
    for var in settings_dict:
        if not var.startswith("__"):
            print(f"  {var} = {settings_dict[var]}")

    return settings_dict

# Check if a local_settings.py path is provided as a parameter

if len(sys.argv) > 1:
    supplied_local_settings = sys.argv[1]
    if not supplied_local_settings.lower().endswith('.py'):
        print(f"WARNING: Provided local_settings file is not a .py file: {supplied_local_settings}")
    elif os.path.exists(supplied_local_settings):
        print(f"Loading local settings from provided argument {supplied_local_settings}")
        # Dynamically load settings from the provided path
        apply_custom_settings_from_file(supplied_local_settings)
    else:
        print(f"WARNING: Provided local_settings.py not found at {supplied_local_settings}")
else:
    # Fallback to default local_settings import if none is supplied
    try:
        from local_settings import *
        print(f"Loading local settings from internal project folder")
    except ImportError:
        print(f"Could not load local settings from internal project folder")
        pass

