from utils.data_loader import DataMixin
import pandas as pd

menu_text = "Export to CSV (MD)"
file_types = "CSV Files (*.md.csv)"

dataMixin = DataMixin.getInstance()

def export_data(fileName: str) -> None:
    """
    Export data to a CSV file.

    Args:
        fileName: Path to the file where data should be exported
    """
    if fileName:
        combined_df = combineData()
        combined_df.to_csv(fileName, index=False)
        print(f"Combined data exported successfully to {fileName}.")

def combineData():
    distances_df = pd.DataFrame(
        dataMixin.distances, columns=['distance'])
    ordered_channel_df = dataMixin.channel_df[dataMixin.channels]
    combined_df = pd.concat([distances_df, ordered_channel_df], axis=1)
    return combined_df