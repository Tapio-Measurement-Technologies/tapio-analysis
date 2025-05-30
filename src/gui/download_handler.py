import requests
import tempfile
import os
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QProgressDialog, QApplication
from PyQt6.QtCore import Qt

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

def download_zip_to_temp(url, parent_widget) -> str | None:
    """Downloads a ZIP file from a URL to a persistent temporary file.

    Args:
        url (str): The URL to download the ZIP file from.
        parent_widget: Parent widget for displaying dialogs.

    Returns:
        str: Path to the downloaded temporary ZIP file, or None on error.
             The caller is responsible for deleting this temporary file.
    """
    tmp_zip_file_path = None
    progress_dialog = QProgressDialog(parent_widget)
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle("Downloading...")
    progress_dialog.setLabelText(f"Downloading file from {url}...")
    progress_dialog.setRange(0, 0)  # Indeterminate progress bar
    progress_dialog.setCancelButton(None) # No cancel button
    # progress_dialog.show() # TODO: Dialog is not displayed due to main thread being blocked
    QApplication.processEvents() # Ensure dialog is displayed

    try:
        # Create a persistent temporary file for the download
        # delete=False means we are responsible for deleting it later.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_handle:
            tmp_zip_file_path = tmp_handle.name

        headers = {'User-Agent': 'Mozilla/5.0'}
        print(f"Downloading from {url} to {tmp_zip_file_path}...")
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status() # Raises HTTPError for bad responses

        with open(tmp_zip_file_path, 'wb') as f_disk:
            # If possible, update progress dialog based on chunks for determinate progress
            # For now, it remains indeterminate.
            for chunk in response.iter_content(chunk_size=8192):
                f_disk.write(chunk)
                QApplication.processEvents() # Keep UI responsive if download is very slow

        progress_dialog.close() # Close on success
        print(f"Download complete: {tmp_zip_file_path}")
        return tmp_zip_file_path

    except requests.exceptions.HTTPError as e:
        progress_dialog.close() # Close on error
        QMessageBox.critical(parent_widget, "Download Error", f"HTTP error: {e.response.status_code} {e.response.reason}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None
    except requests.exceptions.RequestException as e:
        progress_dialog.close() # Close on error
        QMessageBox.critical(parent_widget, "Download Error", f"Failed to download: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None
    except Exception as e:
        progress_dialog.close() # Close on error
        QMessageBox.critical(parent_widget, "Error", f"An unexpected error occurred during download: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None