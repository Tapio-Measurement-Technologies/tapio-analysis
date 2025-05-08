# Tapio Analysis
# Copyright 2025 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout
from typing import List, Tuple, Optional
from utils.types import LoaderModule


def select_loader_dialog(parent, file_extension: str, matching_loaders: List[Tuple[str, LoaderModule]]) -> Optional[LoaderModule]:
    """
    Display a dialog for the user to select which loader to use for a file type.

    Args:
        parent: The parent widget for the dialog
        file_extension: The file extension being loaded
        matching_loaders: List of tuples containing (loader_name, loader_module)

    Returns:
        The selected loader module or None if canceled
    """
    if not matching_loaders:
        return None

    # If only one loader matches, return it directly
    if len(matching_loaders) == 1:
        return matching_loaders[0][1]

    # Create a custom dialog with a dropdown
    dialog = QDialog(parent)
    dialog.setWindowTitle("Select Loader")

    layout = QVBoxLayout()

    # Set dialog text based on file extension
    if file_extension == "all":
        label_text = "Select a file loader to use:"
    else:
        label_text = f"Multiple loaders available for {file_extension} files. Which one would you like to use?"

    label = QLabel(label_text)
    layout.addWidget(label)

    # Create dropdown for loader selection
    combo_box = QComboBox()
    for name, loader in matching_loaders:
        # Use the menu_text attribute if available, otherwise fall back to the name
        display_text = getattr(loader, 'menu_text', name)
        combo_box.addItem(display_text)
    layout.addWidget(combo_box)

    # Add OK and Cancel buttons
    button_layout = QHBoxLayout()
    ok_button = QPushButton("OK")
    cancel_button = QPushButton("Cancel")

    button_layout.addStretch()
    button_layout.addWidget(ok_button)
    button_layout.addWidget(cancel_button)

    layout.addLayout(button_layout)
    dialog.setLayout(layout)

    # Connect buttons to actions
    selected_index = -1

    def on_ok_clicked():
        nonlocal selected_index
        selected_index = combo_box.currentIndex()
        dialog.accept()

    def on_cancel_clicked():
        dialog.reject()

    ok_button.clicked.connect(on_ok_clicked)
    cancel_button.clicked.connect(on_cancel_clicked)

    # Show dialog and get result
    result = dialog.exec()

    if result == QDialog.DialogCode.Accepted and selected_index >= 0:
        return matching_loaders[selected_index][1]

    return None