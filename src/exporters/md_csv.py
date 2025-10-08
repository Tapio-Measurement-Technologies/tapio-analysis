from utils.measurement import Measurement
import pandas as pd

menu_text = "Export raw data to CSV"
file_types = "CSV Files (*.csv)"

def export_data(fileName: str, measurement: Measurement) -> None:
    """
    Export data to a CSV file.

    Args:
        fileName: Path to the file where data should be exported
    """
    if fileName:
        combined_df = combineData(measurement)
        combined_df.to_csv(fileName, index=False)
        print(f"Combined data exported successfully to {fileName}.")

def combineData(measurement: Measurement):
    distances_df = pd.DataFrame(
        measurement.distances, columns=['distance'])
    ordered_channel_df = measurement.channel_df[measurement.channels]
    combined_df = pd.concat([distances_df, ordered_channel_df], axis=1)
    return combined_df