import os
import shutil
import zipfile

import pyzipper
from PyQt6.QtWidgets import QInputDialog, QMessageBox

import utils.zip_utils as zip_utils


class DummyProgressDialog:
    def __init__(self, *args, **kwargs):
        pass

    def setWindowModality(self, *args, **kwargs):
        pass

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setLabelText(self, *args, **kwargs):
        pass

    def setRange(self, *args, **kwargs):
        pass

    def setCancelButton(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def close(self):
        pass


def stub_zip_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(zip_utils, "QProgressDialog", DummyProgressDialog)


def test_zip_unpack_extracts_unencrypted_archive(tmp_path, monkeypatch, qt_app):
    stub_zip_dialogs(monkeypatch)
    archive_path = tmp_path / "plain.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/data.txt", "plain payload")

    extracted_paths, temp_dir = zip_utils.unpack_zip_to_temp_with_password_prompt(
        str(archive_path), None
    )

    try:
        assert extracted_paths is not None
        extracted_file = next(path for path in extracted_paths if path.endswith("data.txt"))
        assert os.path.exists(extracted_file)
        assert open(extracted_file, encoding="utf-8").read() == "plain payload"
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_zip_unpack_extracts_aes_archive_after_password_prompt(
    tmp_path, monkeypatch, qt_app
):
    stub_zip_dialogs(monkeypatch)
    archive_path = tmp_path / "protected.zip"
    with pyzipper.AESZipFile(
        archive_path,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(b"secret")
        archive.writestr("nested/data.txt", "zip payload")

    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("secret", True),
    )

    extracted_paths, temp_dir = zip_utils.unpack_zip_to_temp_with_password_prompt(
        str(archive_path), None
    )

    try:
        assert extracted_paths is not None
        extracted_file = next(path for path in extracted_paths if path.endswith("data.txt"))
        assert os.path.exists(extracted_file)
        assert open(extracted_file, encoding="utf-8").read() == "zip payload"
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
