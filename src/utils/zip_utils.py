import zipfile
import tempfile
import os
import shutil
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit

def unpack_zip_to_temp_with_password_prompt(zip_file_path, parent_widget):
    """Unpacks a ZIP file to a temporary directory, handling passwords.

    Args:
        zip_file_path (str): Path to the ZIP file.
        parent_widget: Parent widget for dialogs.

    Returns:
        tuple: (A list of full paths to extracted files, path to the created persistent temp_dir)
               or (None, None) on failure.
    """
    password_bytes = None
    extracted_file_paths_for_loader = []
    final_persistent_temp_dir = None # This directory will persist if function is successful

    try:
        if not zipfile.is_zipfile(zip_file_path):
            QMessageBox.critical(parent_widget, "Error", "File is not a valid ZIP file.")
            return None, None

        with zipfile.ZipFile(zip_file_path, 'r') as zf:
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
                    if not ok:  # User cancelled password dialog
                        QMessageBox.information(parent_widget, "Cancelled", "Operation cancelled.")
                        return None, None

                    password_text = password_text.strip() # Strip whitespace
                    current_password_bytes = password_text.encode('utf-8')
                    try:
                        file_to_test_info = None
                        for info_member in file_infos:
                            if not info_member.is_dir():
                                file_to_test_info = info_member
                                break

                        if not file_to_test_info:
                            QMessageBox.warning(parent_widget, "No Files in ZIP",
                                                "ZIP contains no files to test password on.")
                            return None, None

                        with zf.open(file_to_test_info, pwd=current_password_bytes) as test_file:
                            test_file.read(1)  # Try to read 1 byte to trigger potential errors
                        password_bytes = current_password_bytes  # Password is correct
                        break
                    except RuntimeError as e_rt:
                        error_message = str(e_rt)
                        print(f"RuntimeError during password test on {file_to_test_info.filename if file_to_test_info else 'an entry'}: {error_message}")

                        if "unsupported compression method" in error_message.lower() or "compression method is not supported" in error_message.lower():
                            QMessageBox.critical(parent_widget, "Unsupported Compression",
                                                 f"The ZIP file '{(os.path.basename(zip_file_path))}' contains files with an unsupported compression method. Please re-zip using a standard method (e.g., Deflate).")
                            # Clean up the temp dir if created, as we can't proceed
                            if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
                            return None, None # Cannot proceed

                        user_message = "Incorrect password or an issue occurred during decryption."
                        if "bad password" in error_message.lower():
                            user_message = "Incorrect password. Please try again."
                        elif "encrypted" in error_message.lower():
                            user_message = "File is encrypted; issue with password or decryption method."
                        QMessageBox.warning(parent_widget, "Password Issue", user_message)
                        # Do not return here, let the loop continue for another password attempt
                    except Exception as e_test:
                        QMessageBox.critical(parent_widget, "Error",
                                           f"Unexpected error testing password: {e_test}")
                        if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
                        return None, None # Critical error, exit loop

            final_persistent_temp_dir = tempfile.mkdtemp() # Create a persistent temp dir
            extracted_file_paths_for_loader = []

            try:
                # Extract directly to the persistent temporary directory
                zf.extractall(path=final_persistent_temp_dir, pwd=password_bytes)

                for item_info in file_infos:
                    if not item_info.is_dir(): # Only interested in files
                        # Sanitize filename from ZIP to prevent issues with leading slashes
                        zip_entry_filename = item_info.filename.lstrip('/\\')

                        # Construct the full path to where the file should have been extracted
                        file_path_in_temp_dir = os.path.join(final_persistent_temp_dir, zip_entry_filename)
                        file_path_in_temp_dir = os.path.normpath(file_path_in_temp_dir)

                        if os.path.isfile(file_path_in_temp_dir): # Verify it exists and is a file
                            extracted_file_paths_for_loader.append(file_path_in_temp_dir)
                        else:
                            # This indicates a problem, e.g. the file from infolist wasn't extracted by extractall
                            # or item_info.filename is not matching what extractall created (e.g. due to path issues).
                            print(f"Warning: Extracted file not found or is not a file after extractall: {file_path_in_temp_dir} (original name in zip: {item_info.filename})")

            except RuntimeError as e_extract: # Often due to password issues on some files / corruption
                QMessageBox.critical(parent_widget, "Extraction Error",
                                     f"Failed to extract ZIP file: {e_extract}")
                if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
                return None, None
            except Exception as e_unhandled_extract: # Other errors during extraction
                QMessageBox.critical(parent_widget, "Extraction Error",
                                     f"An unexpected error occurred during extraction: {e_unhandled_extract}")
                if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
                return None, None

            if not extracted_file_paths_for_loader:
                QMessageBox.warning(parent_widget, "No Files Extracted",
                                  "The ZIP file was empty or contained no usable files after extraction.")
                if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
                return None, None

            return extracted_file_paths_for_loader, final_persistent_temp_dir # Success

    except zipfile.BadZipFile:
        QMessageBox.critical(parent_widget, "Error", "Invalid or corrupted ZIP file.")
        if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
        return None, None
    except Exception as e_main: # Catch-all for other unexpected errors
        QMessageBox.critical(parent_widget, "Processing Error",
                           f"An unexpected error occurred while processing the ZIP: {e_main}")
        if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
        return None, None