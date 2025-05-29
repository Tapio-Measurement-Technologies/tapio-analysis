import requests
import zipfile
import tempfile
import os
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
# from PyQt6.QtCore import Qt # Not directly used but often included

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
    try:
        # 1. Download the file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_handle:
            tmp_zip_file_path = tmp_handle.name

        headers = {'User-Agent': 'Mozilla/5.0'} # Some servers might require a User-Agent
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)

        with open(tmp_zip_file_path, 'wb') as f_disk:
            for chunk in response.iter_content(chunk_size=8192):
                f_disk.write(chunk)

    except requests.exceptions.HTTPError as e:
        QMessageBox.critical(parent_widget, "Download Error", f"HTTP error downloading file: {e.response.status_code} {e.response.reason}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None
    except requests.exceptions.RequestException as e:
        QMessageBox.critical(parent_widget, "Download Error", f"Failed to download file: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None
    except Exception as e: # Catch any other unexpected errors during download/file write
        QMessageBox.critical(parent_widget, "Error", f"An unexpected error occurred during download: {e}")
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path): os.remove(tmp_zip_file_path)
        return None, None

    # 2. Process the ZIP file
    password_bytes = None
    extracted_file_paths_for_loader = []

    try:
        if not zipfile.is_zipfile(tmp_zip_file_path):
            QMessageBox.critical(parent_widget, "Error", "Downloaded file is not a valid ZIP file.")
            return None, None

        with zipfile.ZipFile(tmp_zip_file_path, 'r') as zf:
            file_infos = zf.infolist()
            if not file_infos:
                QMessageBox.warning(parent_widget, "Empty ZIP", "The ZIP file contains no files.")
                return None, None

            is_encrypted = any(finfo.flag_bits & 0x1 for finfo in file_infos)

            if is_encrypted:
                while True:
                    password_text, ok = QInputDialog.getText(parent_widget, "Password Required",
                                                             "Enter password for the ZIP file:",
                                                             echo=QLineEdit.EchoMode.Password)
                    if not ok: # User cancelled password dialog
                        QMessageBox.information(parent_widget, "Cancelled", "Operation cancelled.")
                        return None, None

                    current_password_bytes = password_text.encode('utf-8')
                    try:
                        # Test password by trying to read a byte from the first actual file in the archive
                        file_to_test_info = None
                        for info_member in file_infos:
                            if not info_member.is_dir(): # Make sure it's a file
                                file_to_test_info = info_member
                                break

                        if not file_to_test_info: # Should only happen if ZIP contains only empty dirs
                             QMessageBox.warning(parent_widget, "No Files in ZIP", "ZIP contains no files to test password on.")
                             return None, None

                        with zf.open(file_to_test_info, pwd=current_password_bytes) as test_file:
                            test_file.read(1) # Try to read 1 byte
                        password_bytes = current_password_bytes # Password is correct
                        break
                    except RuntimeError: # Incorrect password or other issue during test
                        QMessageBox.warning(parent_widget, "Incorrect Password", "Incorrect password or unable to decrypt with this password. Please try again.")
                    except Exception as e_test: # Other exceptions during password test
                        QMessageBox.critical(parent_widget, "Error", f"Unexpected error testing password: {e_test}")
                        return None, None

            # 3. Unpack to a temporary directory (context-managed)
            with tempfile.TemporaryDirectory() as tmp_extract_dir:
                try:
                    zf.extractall(path=tmp_extract_dir, pwd=password_bytes)
                except RuntimeError as e_extract:
                     QMessageBox.critical(parent_widget, "Extraction Error", f"Failed to extract ZIP file (possibly due to password issues on some files or corruption): {e_extract}")
                     return None, None
                except Exception as e_unhandled_extract:
                     QMessageBox.critical(parent_widget, "Extraction Error", f"An unexpected error occurred during extraction: {e_unhandled_extract}")
                     return None, None

                for item_info in file_infos: # Use the fetched file_infos
                    if not item_info.is_dir():
                        full_path = os.path.join(tmp_extract_dir, item_info.filename)
                        extracted_file_paths_for_loader.append(os.path.normpath(full_path))

                if not extracted_file_paths_for_loader:
                    QMessageBox.warning(parent_widget, "No Files Extracted", "The ZIP file was empty or contained only directories after extraction.")
                    return None, None

                # 4. Return file details for the main window to handle loading
                first_file_ext = os.path.splitext(extracted_file_paths_for_loader[0])[1].lower() if extracted_file_paths_for_loader else "all"

                return first_file_ext, extracted_file_paths_for_loader

    except zipfile.BadZipFile:
        QMessageBox.critical(parent_widget, "Error", "Invalid or corrupted ZIP file.")
        return None, None
    except Exception as e_main:
        QMessageBox.critical(parent_widget, "Processing Error", f"An unexpected error occurred while processing the ZIP file: {e_main}")
        return None, None
    finally:
        if tmp_zip_file_path and os.path.exists(tmp_zip_file_path):
            os.remove(tmp_zip_file_path)