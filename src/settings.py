import os

import importlib.util
import sys
from utils.types import MainWindowSection, MainWindowSectionModule
from utils.cli_args import parse_startup_args

DEBUG = False

# Meters per minute
PAPER_MACHINE_SPEED_DEFAULT = 1600.00
FILTER_NUMTAPS = 2500

REPORT_ADDITIONAL_INFO_DEFAULT = f"Speed at reel: {PAPER_MACHINE_SPEED_DEFAULT:.0f} m/min\nGrammage:"
MD_REPORT_TEMPLATE_DEFAULT = None
CD_REPORT_TEMPLATE_DEFAULT = None

REPORT_FORMAT_DEFAULT = 'latex'

REPORT_SECTION_NEWPAGE = True


FORCE_PRIMARY_SCALE_SUPPLEMENTARY = False

LOADERS_DIR = 'loaders'
EXPORTERS_DIR = 'exporters'
ANALYSIS_DIR = 'analyses'
ANALYSIS_SECTIONS = [
    MainWindowSection(
        name="MD Analysis",
        modules=[
            MainWindowSectionModule(
                module_name="time_domain",         type="MD"),
            MainWindowSectionModule(
                module_name="spectrum",            type="MD"),
            MainWindowSectionModule(
                module_name="spectrogram",         type="MD"),
            MainWindowSectionModule(
                module_name="channel_correlation", type="MD"),
            MainWindowSectionModule(
                module_name="correlation_matrix",  type="MD"),
            MainWindowSectionModule(
                module_name="formation",           type="MD"),
            MainWindowSectionModule(
                module_name="coherence",           type="MD"),
            MainWindowSectionModule(
                module_name="cepstrum",            type="MD")
        ]
    ),
    MainWindowSection(
        name="CD Analysis",
        modules=[
            MainWindowSectionModule(module_name="find_samples"),
            MainWindowSectionModule(
                module_name="cd_profile",           type="CD"),
            MainWindowSectionModule(
                module_name="cd_profile_waterfall", type="CD"),
            MainWindowSectionModule(
                module_name="spectrum",             type="CD"),
            MainWindowSectionModule(
                module_name="spectrogram",          type="CD"),
            MainWindowSectionModule(
                module_name="channel_correlation",  type="CD"),
            MainWindowSectionModule(
                module_name="correlation_matrix",   type="CD"),
            MainWindowSectionModule(
                module_name="vca",                  type="CD"),
            MainWindowSectionModule(
                module_name="formation",            type="CD"),
            MainWindowSectionModule(
                module_name="coherence",            type="CD")
        ]
    ),
    MainWindowSection(
        name="Reports",
        modules=[
            MainWindowSectionModule(
                module_name="report", analysis_name="MD Report", type="MD", callback_name="openReport"),
            MainWindowSectionModule(
                module_name="report", analysis_name="CD Report", type="CD", callback_name="openReport")
        ]
    )
]
ANALYSES_EXCLUDED_FROM_REPORT = ["sos", "find_samples"]

UPDATE_ON_SLIDE = False
IGNORE_CHANNELS = ["Density"]
# Channels whose data is at least this fraction non-finite are dropped on load.
# A disconnected sensor or a failed calibration yields an all-NaN channel that
# cannot be plotted or correlated. Set to None to keep every channel.
DROP_CHANNEL_NAN_FRACTION = 1.0
CORRELATION_MATRIX_SAMPLE_LIMIT = 2000
CORRELATION_MATRIX_HISTOGRAM_BINS = 20
CORRELATION_MATRIX_LABEL_FONT_SIZE = 8
CORRELATION_MATRIX_WINDOW_SIZE = (1000, 600)
CORRELATION_MATRIX_TICK_LABEL_TARGET_CHARS = 5


# Formation analysis settings
FORMATION_TRANSMISSION_CHANNEL = "Transmission"
FORMATION_BW_CHANNEL = "BW"
FORMATION_WINDOW_LENGTH = 400
# Unit of the formation index f_N = sigma_b / sqrt(b): the square root of the
# basis weight unit.
FORMATION_INDEX_UNIT = "(g/m^2)^0.5"
FORMATION_WINDOW_SIZE = (1000, 600)

SPECTROGRAM_COLORMAP = "viridis"

# Spectrogram amplitude scaling.
# scipy/matplotlib spectrograms return a power spectral DENSITY, while the
# Spectrum window uses a power SPECTRUM. Without the conversion below the
# spectrogram amplitude is off by sqrt(ENBW), which also changes with the
# window length. Leave True so spectrogram amplitudes match the Spectrum
# window; set False only to reproduce the legacy (uncorrected) levels.
SPECTROGRAM_AMPLITUDE_DENSITY_CORRECTION = True

# Colour scale of the spectrogram image.
#   "relative" - vmax = SPECTROGRAM_COLOR_SCALE_FACTOR * mean amplitude of the
#                visible band. Autoscales per plot so weak phenomena stay
#                visible in every measurement. This is the default.
#   "full"     - vmax = max amplitude of the visible band.
#   "fixed"    - vmin/vmax taken from SPECTROGRAM_FIXED_CLIM for the channel,
#                so two measurements can be compared directly.
SPECTROGRAM_COLOR_SCALE_MODE = "relative"
SPECTROGRAM_COLOR_SCALE_FACTOR = 3.0
# Per channel (vmin, vmax) in channel units, used when the mode is "fixed".
SPECTROGRAM_FIXED_CLIM = {}
# Print the numeric colour range on the colour bar label so a relative scale is
# not mistaken for an absolute one.
SPECTROGRAM_SHOW_COLOR_SCALE_RANGE = True

MAX_HARMONICS_DISPLAY = 10
MAX_HARMONICS_FREQUENCY_ESTIMATOR = 1

# "Refine frequency selection" search window. The window is the smaller of a
# fraction of the visible frequency axis and a fraction of the selected
# frequency. The second cap matters for low-frequency peaks: without it a peak
# at 0.03 1/m on a 0-39 1/m axis would be searched over +/-0.39 1/m and the
# estimator could return a near-DC bin, i.e. a wavelength longer than the sample.
FREQUENCY_REFINEMENT_VIEW_FRACTION = 0.01
FREQUENCY_REFINEMENT_MAX_RELATIVE = 0.10

# CD Find samples settings
CD_SAMPLE_LENGTH_SLIDER_MIN = 2  # Minimum allowed sample length in meters
CD_SAMPLE_LENGTH_SLIDER_MAX = 15  # Maximum allowed sample length in meters
CD_SAMPLE_LENGTH_SLIDER_STEP = 0.01

# How CD strips of unequal length are trimmed to a common length. This decides
# which physical CD position index 0 of every profile refers to, and therefore
# how well short wavelength CD structure survives averaging.
#   "left"   keep the start, so every profile begins at its leading tape
#   "right"  keep the end, so every profile ends at its trailing tape
#   "center" cut equally from both ends (shifts strips relative to each other)
CD_SEGMENT_ALIGNMENT = "center"

# Tape width which will be cut off from all CD samples
TAPE_WIDTH_MM = 65.00
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
TIME_DOMAIN_PLAYBACK_MAX_OCTAVES = 6
TIME_DOMAIN_PLAYBACK_OUTPUT_SAMPLE_RATE = 44100


TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT_MULTIPLIER = 1
TIME_DOMAIN_ANALYSIS_DISPLAY_UNIT = "m"


SPECTRUM_WINDOW_SIZE = (1200, 600)
SPECTRUM_WELCH_WINDOW = "hann"
SPECTRUM_AMPLITUDE_SCALING = 1  # Set to 2 for peak-to-peak, 1/sqrt(2) for RMS

# Coherence needs several Welch segments to mean anything: with a single segment
# the magnitude-squared coherence is identically 1 at every frequency regardless
# of the data, and with a handful the estimate sits well above zero even for
# completely unrelated channels. The defaults below are chosen so a coherence
# plot can be read at face value; the analysis refuses to plot rather than show
# an estimate built on fewer segments than this.
COHERENCE_MIN_SEGMENTS = 8
# Target number of *independent* (overlap-corrected) segments. The default
# segment length is reduced automatically if the selected analysis range is too
# short to supply this many, so the estimate stays trustworthy on short CD
# strips as well as long MD records.
COHERENCE_TARGET_EFFECTIVE_SEGMENTS = 16
# Confidence level used for the internally computed significance threshold.
COHERENCE_SIGNIFICANCE_LEVEL = 0.95
# The threshold is available on the controller for export and debugging; it is
# not drawn, because the defaults above keep the noise floor low enough that the
# plot can be read directly.
COHERENCE_SHOW_SIGNIFICANCE_LINE = False
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

# Coherence analysis segment settings. Kept separate from the spectrum settings
# because coherence trades frequency resolution for segment count, while the
# spectrum wants the opposite.
MD_COHERENCE_DEFAULT_LENGTH = 20000
MD_COHERENCE_OVERLAP = 0.5
MD_COHERENCE_LENGTH_SLIDER_MIN = 500
MD_COHERENCE_LENGTH_SLIDER_MAX = 100000

CD_COHERENCE_DEFAULT_LENGTH = 1000
CD_COHERENCE_OVERLAP = 0.5
CD_COHERENCE_LENGTH_SLIDER_MIN = 100
CD_COHERENCE_LENGTH_SLIDER_MAX = 10000


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
# THIS will flip loaded data in the parquet loader
FLIP_LOADED_DATA = False

CD_PROFILE_WINDOW_SIZE = (1200, 600)
CD_PROFILE_WATERFALL_WINDOW_SIZE = (1100, 1045)


CD_PROFILE_BAND_PASS_LOW_DEFAULT_1M = 0
CD_PROFILE_BAND_PASS_HIGH_DEFAULT_1M = 30
CD_PROFILE_RANGE_LOW_DEFAULT = 0
CD_PROFILE_RANGE_HIGH_DEFAULT = 1


CD_PROFILE_WATERFALL_OFFSET_DEFAULT = 10  # Relative offset in percent (e.g., 10 = 10% of mean profile value)
CD_PROFILE_WATERFALL_DEFAULT_CHANNEL_OFFSETS = None

# Example for setting default offsets per channel, if desired
# NOTE: Disables manual adjustment of offsets in the UI
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

# Waterfall plot settings (relative to mean profile value, in percent)
WATERFALL_OFFSET_LOW_DEFAULT = 0
WATERFALL_OFFSET_HIGH_DEFAULT = 100

MD_REPORT_SAMPLE_IMAGE_PATH = None
CD_REPORT_SAMPLE_IMAGE_PATH = None
REPORT_LOGO_PATH = None
REPORT_ENABLE_ANALYSIS_TITLE = False


SOS_HARMONICS = 10
# Number of points in the reconstructed SOS revolution. Decoupled from the
# sampling rate so the angular resolution of the polar plot is the same at every
# frequency.
SOS_REVOLUTION_POINTS = 720

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
# Examples:
# def calc_bulk(dataframe):
#     return (dataframe['Caliper']) / dataframe['Basis Weight']

BASIS_WEIGHT_CHANNEL_CANDIDATES = ["BW", "Basis Weight", "Basis Weight 1", "Basis Weight 2"]
CALIPER_CHANNEL_CANDIDATES = ["Caliper", "Dicke", "Paksuus"]


def find_channel(dataframe, candidates, channel_label):
    for candidate in candidates:
        candidate_key = candidate.strip().casefold()
        for column in dataframe.columns:
            if str(column).strip().casefold() == candidate_key:
                return column

    raise ValueError(
        f"{channel_label} channel not found. Tried: {', '.join(candidates)}"
    )


def find_basis_weight_channel(dataframe):
    return find_channel(
        dataframe,
        BASIS_WEIGHT_CHANNEL_CANDIDATES,
        "Basis Weight"
    )


def find_caliper_channel(dataframe):
    return find_channel(
        dataframe,
        CALIPER_CHANNEL_CANDIDATES,
        "Caliper"
    )


def calc_density(dataframe):
    """Apparent density in g/cm^3.

    Basis weight is g/m^2 and caliper is um. For a 1 cm^2 patch the mass is
    BW * 1e-4 g and the volume is caliper * 1e-4 cm^3, so the unit conversions
    cancel and the density in g/cm^3 is simply BW / caliper.
    """
    bw_name = find_basis_weight_channel(dataframe)
    caliper_name = find_caliper_channel(dataframe)
    return dataframe[bw_name] / dataframe[caliper_name]

def calc_bulk(dataframe):
    """Bulk (specific volume) in cm^3/g, the reciprocal of density."""
    bw_name = find_basis_weight_channel(dataframe)
    caliper_name = find_caliper_channel(dataframe)
    return dataframe[caliper_name] / dataframe[bw_name]

def calc_relative_ash(dataframe):
    if 'Ash' not in dataframe.columns:
        raise ValueError("Ash channel not found")
    bw_name = find_basis_weight_channel(dataframe)
    return dataframe['Ash'] / dataframe[bw_name]

# Original examples:
# def calc_density(dataframe):
#     return (dataframe['Basis Weight']) / dataframe['Caliper']

# def calc_relative_ash(dataframe):
#     return (dataframe['Ash']) / dataframe['Basis Weight']

CALCULATED_CHANNELS = [
    {"name": "Density", "unit": "g/cm^3", "function": calc_density},
    {"name": "Bulk", "unit": "cm^3/g", "function": calc_bulk},
    {"name": "Ash (relative)", "unit": "", "function": calc_relative_ash}
]


MULTIPLE_SELECT_MODE = False

DOUBLE_SLIDER_FINE_CONTROL_FACTOR = 0.1  # 10% of normal movement
DOUBLE_SLIDER_HANDLE_RADIUS = 8  # px, adjust as needed

SPECTRUM_TITLE_SHOW = True
SPECTRUM_AUTO_DETECT_PEAKS = None

CD_SPECTRUM_LOGARITHMIC_SCALE = False
MD_SPECTRUM_LOGARITHMIC_SCALE = False

MD_SPECTRUM_SECONDARY_X_LABEL_EXPR = "f'Frequency [Hz] at machine speed {self.machine_speed:.1f} m/min'"


# SPECTRUM_MODE = "spectrum_of_mean_profile"  # or "mean_spectrum_of_profiles"
SPECTRUM_MODE = "mean_spectrum_of_profiles"  # or "spectrum_of_mean_profile"

# Cepstrum: dynamic range in dB below the spectral peak at which the power
# spectrum is floored before the log is taken. Bins quieter than this contribute
# no cepstral content. Too large and the near-empty bins between harmonics
# dominate and bury the rahmonics; too small and weak harmonic families are lost.
CEPSTRUM_DYNAMIC_RANGE_DB = 30.0

# Cepstrum: the frequency range, in 1/m, plotted and searched for rahmonics by
# default. The cepstrum is drawn against the frequency of the harmonic family it
# finds, so a peak sits on the same tick as the fundamental it explains in the
# spectrum, and these bounds read the same way as the spectrum's.
#   MIN bounds the longest period shown. A rahmonic family comes from a rotating
#   element, so the interesting periods are roll circumferences: 0.2 1/m is a 5 m
#   circumference, and below that the axis runs to half a Welch segment, which is
#   hundreds of metres of empty plot.
#   MAX cuts off the short periods, and with them the hump every cepstrum has
#   near quefrency zero. That hump comes from the broad shape of the spectrum
#   rather than from any periodicity, and it wins the peak search if left in.
#   20 1/m is a 5 cm period.
# Note that the cepstrum resolves a constant step in period, so on a frequency
# axis its resolution falls off as f squared: bins crowd together at the left of
# the range and spread out towards the right. CEPSTRUM_SHOW_BINS draws the bin
# positions so that this is visible rather than implied.
CEPSTRUM_FREQUENCY_RANGE_MIN_DEFAULT = 0.2
CEPSTRUM_FREQUENCY_RANGE_MAX_DEFAULT = 20.0
CEPSTRUM_SHOW_BINS = True


SPECTRUM_SHOW_HARMONICS_NUMBERS = True

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

PQ_LOADER_GENERATE_DISTANCES = False
# Samples discarded from the start of a parquet record while acquisition settles.
PQ_LOADER_DISCARD_LEADING_SAMPLES = 1000
# Acquisition rate of the parquet data, used to derive the machine speed from
# the distance column.
PQ_LOADER_ACQUISITION_HZ = 1000
PQ_LOADER_GENERATE_DISTANCES_SAMPLE_STEP_DEFAULT = 0.001

LOG_WINDOW_SHOW_TIMESTAMPS = True
LOG_WINDOW_MAX_LINES = 1000
CRASH_DIALOG_CONTACT_EMAIL = "info@tapiotechnologies.com"


def get_py_file_vars(py_file_path):
    """
    Returns variables from python file dynamically using importlib.
    """
    if os.path.exists(py_file_path):
        spec = importlib.util.spec_from_file_location(
            "imported_module", py_file_path)
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
startup_args = parse_startup_args()

if startup_args.settings_path:
    supplied_local_settings = startup_args.settings_path
    if not supplied_local_settings.lower().endswith('.py'):
        print(
            f"WARNING: Provided local_settings file is not a .py file: {supplied_local_settings}")
    elif os.path.exists(supplied_local_settings):
        print(
            f"Loading local settings from provided argument {supplied_local_settings}")
        apply_custom_settings_from_file(supplied_local_settings)
    else:
        print(
            f"WARNING: Provided local_settings.py not found at {supplied_local_settings}")
else:
    # Fallback to default local_settings import if none is supplied
    try:
        from local_settings import *
        print(f"Loading local settings from internal project folder")
    except ImportError:
        print(f"Could not load local settings from internal project folder")
        pass
