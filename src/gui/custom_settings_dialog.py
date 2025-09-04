from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QMessageBox)
from PyQt6.QtCore import Qt
import settings


class CustomSettingsConfirmationDialog(QDialog):
    def __init__(self, settings_file_path, settings_vars, parent=None):
        super().__init__(parent)
        self.settings_file_path = settings_file_path
        self.settings_vars = settings_vars
        self.accepted_settings = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("Custom Settings Confirmation")
        self.setModal(True)
        self.resize(600, 400)

        layout = QVBoxLayout()

        # Title label
        title_label = QLabel(f"Apply custom settings from: {self.settings_file_path}")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # Description label
        desc_label = QLabel("The following settings will be applied for this session. Review and confirm:")
        layout.addWidget(desc_label)

        # Read-only text box showing the settings
        self.settings_text = QTextEdit()
        self.settings_text.setReadOnly(True)

        # Format settings for display
        settings_display = self._format_settings_for_display()
        self.settings_text.setPlainText(settings_display)

        layout.addWidget(self.settings_text)

        # Buttons
        button_layout = QHBoxLayout()

        self.apply_button = QPushButton("Apply Settings")
        self.apply_button.clicked.connect(self.accept_settings)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _format_settings_for_display(self):
        """Format the settings dictionary for human-readable display."""
        lines = []

        # Filter out private/system variables
        filtered_vars = {k: v for k, v in self.settings_vars.items()
                        if not k.startswith('__') and not callable(v)}

        if not filtered_vars:
            return "No settings variables found to apply."

        lines.append("Settings to be applied:")
        lines.append("=" * 50)

        for key, value in sorted(filtered_vars.items()):
            # Format the value display
            if isinstance(value, str):
                value_display = f'"{value}"'
            elif isinstance(value, (list, tuple)):
                if len(str(value)) > 100:
                    value_display = f"{type(value).__name__} with {len(value)} items"
                else:
                    value_display = str(value)
            elif isinstance(value, dict):
                if len(str(value)) > 100:
                    value_display = f"dict with {len(value)} keys"
                else:
                    value_display = str(value)
            else:
                value_display = str(value)

            lines.append(f"{key} = {value_display}")

        return "\n".join(lines)

    def accept_settings(self):
        """Apply the settings and close the dialog."""
        try:
            # Filter settings to only include non-private, non-callable variables
            filtered_vars = {k: v for k, v in self.settings_vars.items()
                           if not k.startswith('__') and not callable(v)}

            if filtered_vars:
                settings.apply_custom_settings_from_dict(filtered_vars)
                self.accepted_settings = filtered_vars
                self.accept()
            else:
                QMessageBox.information(self, "No Settings",
                                      "No valid settings found to apply.")
        except Exception as e:
            QMessageBox.critical(self, "Error",
                               f"Error applying custom settings: {str(e)}")

    def get_accepted_settings(self):
        """Return the settings that were accepted, or None if cancelled."""
        return self.accepted_settings


def show_custom_settings_dialog(settings_file_path, settings_vars, parent=None):
    """
    Show the custom settings confirmation dialog.

    Args:
        settings_file_path: Path to the settings file
        settings_vars: Dictionary of variables from the settings file
        parent: Parent widget

    Returns:
        tuple: (accepted, applied_settings) where accepted is bool and
               applied_settings is dict or None
    """
    dialog = CustomSettingsConfirmationDialog(settings_file_path, settings_vars, parent)
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted:
        return True, dialog.get_accepted_settings()
    else:
        return False, None