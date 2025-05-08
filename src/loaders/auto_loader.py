# Tapio Analysis
# Copyright 2024 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Auto Loader module that tries all available loaders until one successfully loads the data.
"""

from utils.measurement import Measurement
import logging

# Define class variables required by the LoaderModule protocol
menu_text = "Auto load"
file_types = "All Supported Files (*.*)"
menu_priority = 1

def load_data(fileNames: list[str]) -> Measurement | None:
    """
    Try to load data using all available loaders until one succeeds.

    Args:
        fileNames: List of file paths to load data from

    Returns:
        Measurement object if loading was successful, None otherwise
    """
    if not fileNames:
        logging.warning("No files provided to auto_loader")
        return None

    # Import store here to avoid circular import
    from utils import store

    # Try each loader in sequence
    for loader_name, loader in store.loaders.items():
        # Skip ourselves to avoid infinite recursion
        if loader_name == "auto_loader":
            continue

        logging.info(f"Trying to load files with {loader_name}")
        try:
            measurement = loader.load_data(fileNames)
            if measurement is not None:
                logging.info(f"Successfully loaded files with {loader_name}")
                return measurement
        except Exception as e:
            logging.debug(f"Loader {loader_name} failed with error: {str(e)}")
            continue

    logging.warning("All loaders failed to load the provided files")
    return None

# Function to update file_types after all loaders are loaded
def update_file_types():
    """Update the file_types with all supported file types from other loaders."""
    from utils import store

    all_file_types = []
    for loader_name, loader in store.loaders.items():
        if loader_name != "auto_loader" and hasattr(loader, 'file_types') and loader.file_types:
            all_file_types.append(loader.file_types)

    # Only update if we found other loaders
    if all_file_types:
        global file_types
        file_types = ";;".join(all_file_types)
