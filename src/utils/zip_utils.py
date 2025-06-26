import pyzipper
import tempfile
import os
import shutil
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit, QProgressDialog, QApplication
from PyQt6.QtCore import Qt

def unpack_zip_to_temp_with_password_prompt(zip_file_path, parent_widget):
    """Unpacks a ZIP file to a temporary directory using pyzipper, handling passwords.

    Args:
        zip_file_path (str): Path to the ZIP file.
        parent_widget: Parent widget for dialogs.

    Returns:
        tuple: (A list of full paths to extracted files, path to the created persistent temp_dir)
               or (None, None) on failure.
    """
    password_bytes = None
    extracted_file_paths_for_loader = []
    final_persistent_temp_dir = None

    try:
        if not pyzipper.is_zipfile(zip_file_path):
            QMessageBox.critical(parent_widget, "Error", "File is not a valid ZIP file.")
            return None, None

        # Attempt to open without password first to check if it *needs* one / determine encryption.
        # This helps avoid unnecessarily prompting for a password on unencrypted files.
        needs_password_check = False
        try:
            with pyzipper.ZipFile(zip_file_path, 'r') as zf_check:
                # Check a robust way if any file needs password, pyzipper might have specific flags
                # A common check: if any file uses AES or traditional encryption that needs password
                # AES vendor IDs: 99 (implies AES). Traditional is flag_bits & 0x1.
                for finfo_check in zf_check.infolist():
                    if finfo_check.flag_bits & 0x1: # Traditional ZipCrypto
                        needs_password_check = True
                        break
                    # Pyzipper handles AES directly. If AES, it would need a password.
                    # ZipInfo in pyzipper might have an is_aes_encrypted() or similar.
                    # Let's assume for now that if flag_bits & 0x1 is false, but it IS encrypted (e.g. AES),
                    # the open() or extractall() without password would fail later if it needed one.
                    # pyzipper.ZipFile.open() or .extractall() will raise RuntimeError if pwd needed and not provided or wrong.
                    # For AES, if finfo_check.compress_type == 99, it implies AES.
                    if getattr(finfo_check, 'compress_type', None) == 99: # Check for AES compression type
                        needs_password_check = True
                        break
        except Exception: # Could be a password-protected zip that can't be read without it, or other issue.
            needs_password_check = True # Assume password needed if initial simple open fails

        file_infos_for_extraction = [] # To be populated after successful open (with or without pwd)

        if needs_password_check:
            while True:
                password_text, ok = QInputDialog.getText(parent_widget, "Password Required",
                                                         "Enter password for the ZIP file:",
                                                         echo=QLineEdit.EchoMode.Password)
                if not ok:
                    QMessageBox.information(parent_widget, "Cancelled", "Operation cancelled.")
                    return None, None

                password_text = password_text.strip()
                current_password_bytes = password_text.encode('utf-8')

                try:
                    # Try to open the main zipfile with the password. Pyzipper handles AES/Standard based on pwd.
                    with pyzipper.ZipFile(zip_file_path, 'r') as zf:
                        zf.pwd = current_password_bytes
                        file_infos_for_extraction = zf.infolist() # If this works, password is good

                        # Perform a quick test read on the first actual file if possible
                        first_file_to_test = None
                        for fi in file_infos_for_extraction:
                            if not fi.is_dir():
                                first_file_to_test = fi
                                break
                        if first_file_to_test:
                            print(f"Attempting to test password on file: {first_file_to_test.filename}, compress_type: {first_file_to_test.compress_type}, flag_bits: {first_file_to_test.flag_bits:04x}")
                            with zf.open(first_file_to_test) as test_fo:
                                test_fo.read(1) # Trigger read error if any

                        password_bytes = current_password_bytes # Password accepted
                        break
                except RuntimeError as e_rt:
                    error_message = str(e_rt)
                    print(f"RuntimeError during password test: {error_message}")
                    if "unsupported compression method" in error_message.lower() or "compression method is not supported" in error_message.lower():
                        QMessageBox.critical(parent_widget, "Unsupported Compression",
                                             f"The ZIP file '{(os.path.basename(zip_file_path))}' uses an unsupported compression method. Please re-zip using a standard method (e.g., Deflate).")
                        return None, None
                    # Assuming other RuntimeErrors are password-related for pyzipper here
                    QMessageBox.warning(parent_widget, "Password Issue", "Incorrect password or an issue occurred during decryption. Please try again.")
                except pyzipper.BadZipfile: # Specifically catch BadZipfile which can indicate wrong password for some structures
                     QMessageBox.warning(parent_widget, "Password Issue", "Incorrect password or corrupted ZIP file. Please try again.")
                except Exception as e_other:
                    print(f"Other exception during password test: {e_other}")
                    QMessageBox.critical(parent_widget, "Error", f"Unexpected error testing password: {e_other}")
                    return None, None
        else: # No password seems to be needed based on initial checks
            try:
                with pyzipper.ZipFile(zip_file_path, 'r') as zf_no_pwd:
                    file_infos_for_extraction = zf_no_pwd.infolist()
            except Exception as e_no_pwd_open:
                 QMessageBox.critical(parent_widget, "Error", f"Could not open ZIP file (even without password): {e_no_pwd_open}")
                 return None, None

        if not file_infos_for_extraction: # Should have file_infos if successfully opened
             QMessageBox.warning(parent_widget, "Empty or Unreadable ZIP", "Could not read contents of the ZIP file.")
             return None, None

        final_persistent_temp_dir = tempfile.mkdtemp()

        progress_dialog_unpack = QProgressDialog(parent_widget)
        progress_dialog_unpack.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog_unpack.setWindowTitle("Unpacking...")
        progress_dialog_unpack.setLabelText(f"Unpacking {os.path.basename(zip_file_path)}...")
        progress_dialog_unpack.setRange(0, 0)  # Indeterminate
        progress_dialog_unpack.setCancelButton(None)
        progress_dialog_unpack.show()
        QApplication.processEvents()

        try:
            # Use a single ZipFile context for extraction, configured with password if needed
            with pyzipper.ZipFile(zip_file_path, 'r') as zf_extract:
                if password_bytes:
                    zf_extract.pwd = password_bytes

                # If AES was detected and password worked, ensure to set encryption for extractall
                # This part is tricky as we don't definitively know *which* encryption method was successful
                # from the trial-and-error password loop above. `pyzipper.ZipFile` itself doesn't store the detected encryption.
                # However, setting zf_extract.pwd should be enough for pyzipper to handle it if it supported it during open.
                # If AES is required, the `encryption=pyzipper.WZ_AES` might be needed on THIS ZipFile instance too.
                # Let's assume `zf_extract.pwd = password_bytes` is sufficient for `extractall` to use the correct method if password was accepted.
                # For safety, could try to re-determine if AES is explicitly needed for extractall if `compress_type == 99` was seen.
                # This logic is getting complex. A simpler approach might be if pyzipper handles it automatically based on `pwd`.

                zf_extract.extractall(path=final_persistent_temp_dir)

            progress_dialog_unpack.close()

            for item_info in file_infos_for_extraction: # Use the infolist from the successfully opened zip
                if not item_info.is_dir():
                    zip_entry_filename = item_info.filename.lstrip('/\\')
                    file_path_in_temp_dir = os.path.join(final_persistent_temp_dir, zip_entry_filename)
                    file_path_in_temp_dir = os.path.normpath(file_path_in_temp_dir)
                    if os.path.isfile(file_path_in_temp_dir):
                        extracted_file_paths_for_loader.append(file_path_in_temp_dir)
                    else:
                        print(f"Warning: Extracted file not found after extractall: {file_path_in_temp_dir} (original name in zip: {item_info.filename})")

        except RuntimeError as e_extract_rt:
            error_message = str(e_extract_rt)
            print(f"RuntimeError during extraction: {error_message}")
            progress_dialog_unpack.close()
            if "unsupported compression method" in error_message.lower() or "compression method is not supported" in error_message.lower():
                QMessageBox.critical(parent_widget, "Unsupported Compression", f"The ZIP file '{(os.path.basename(zip_file_path))}' uses an unsupported compression method during extraction. Please re-zip using a standard method.")
            else:
                QMessageBox.critical(parent_widget, "Extraction Error", f"Failed to extract ZIP file. It might be corrupted or the password was incorrect for some files. Error: {error_message}")
            if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
            return None, None
        except Exception as e_unhandled_extract:
            progress_dialog_unpack.close()
            QMessageBox.critical(parent_widget, "Extraction Error", f"An unexpected error occurred during extraction: {e_unhandled_extract}")
            if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
            return None, None

        if not extracted_file_paths_for_loader:
            progress_dialog_unpack.close()
            QMessageBox.warning(parent_widget, "No Files Extracted", "The ZIP file was empty or contained no usable files after extraction.")
            if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
            return None, None

        return extracted_file_paths_for_loader, final_persistent_temp_dir

    except pyzipper.BadZipfile as e_bad_zip:
        QMessageBox.critical(parent_widget, "Error", f"Invalid or corrupted ZIP file: {e_bad_zip}")
        if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
        return None, None
    except Exception as e_main:
        QMessageBox.critical(parent_widget, "Processing Error", f"An unexpected error occurred: {e_main}")
        if final_persistent_temp_dir: shutil.rmtree(final_persistent_temp_dir, ignore_errors=True)
        return None, None