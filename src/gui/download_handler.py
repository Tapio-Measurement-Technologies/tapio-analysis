import requests
import tempfile
import os
from PyQt6.QtWidgets import QInputDialog, QMessageBox
from utils.zip_utils import unpack_zip_to_temp_with_password_prompt

def prompt_for_url(parent_widget):
    """Prompts the user to enter a URL.

    Args:
        parent_widget: The parent widget for the dialog.

    Returns:
        The URL string if entered, or None if cancelled.
    """
    url, ok = QInputDialog.getText(parent_widget, "Download Measurement", "Enter URL of the ZIP file:")
    if ok and url:
        return url.strip()
    return None

def download_and_process_zip(url, parent_widget):
    """Downloads a ZIP file from a URL, prompts for password if needed,
    unpacks it, and returns the paths of the extracted files.

    Args:
        url (str): The URL to download the ZIP file from.
        parent_widget: Parent widget for displaying dialogs (e.g., QMessageBox, QInputDialog).

    Returns:
        tuple: (first_file_extension, list_of_extracted_file_paths) or (None, None) on error.
    """
    tmp_zip_file_path = None
    created_temp_dir_path = None # To store the path of the temp dir created by unpack_zip
    try:
        # 1. Download the file to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_handle:
            tmp_zip_file_path = tmp_handle.name

        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status()

        with open(tmp_zip_file_path, 'wb') as f_disk:
            for chunk in response.iter_content(chunk_size=8192):
                f_disk.write(chunk)

    except requests.exceptions.HTTPError as e:
        QMessageBox.critical(parent_widget, "Download Error", f"HTTP error: {e.response.status_code} {e.response.reason}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None, None
    except requests.exceptions.RequestException as e:
        QMessageBox.critical(parent_widget, "Download Error", f"Failed to download: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None, None
    except Exception as e:
        QMessageBox.critical(parent_widget, "Error", f"Download error: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None, None

    # 2. Unpack the downloaded ZIP file using the utility function
    extracted_file_paths, created_temp_dir_path = unpack_zip_to_temp_with_password_prompt(tmp_zip_file_path, parent_widget)

    # Clean up the downloaded ZIP file immediately after unpacking attempt
    if tmp_zip_file_path and os.path.exists(tmp_zip_file_path):
        os.remove(tmp_zip_file_path)

    if not extracted_file_paths:
        # unpack_zip_to_temp_with_password_prompt already showed an error message
        # If created_temp_dir_path exists here, it implies unpack_zip_to_temp_with_password_prompt failed after creating the dir but before returning paths.
        # The unpack_zip_to_temp_with_password_prompt should handle its own partial cleanup on failure.
        return None, None, None # Adjusted to return three values for consistency on error

    # 3. Return file details for the main window to handle loading
    first_file_ext = "all"

    return first_file_ext, extracted_file_paths, created_temp_dir_path