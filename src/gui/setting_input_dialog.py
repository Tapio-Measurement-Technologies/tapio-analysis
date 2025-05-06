from PyQt6.QtWidgets import QInputDialog, QMessageBox
import sys
import importlib
import settings

def open_setting_input_dialog(parent_widget):
    """Opens a dialog to get a setting key and value from the user, then updates the setting."""
    # Step 1: Ask user for the setting key
    setting_key, ok = QInputDialog.getText(
        parent_widget, "Enter Setting Name", "Setting Key:")

    if not ok or not setting_key:
        return  # User canceled the input

    # Step 2: Check if the key exists in settings
    if not hasattr(settings, setting_key):
        QMessageBox.warning(parent_widget, "Error", f"Setting '{setting_key}' does not exist.")
        return

    # Step 3: Get the current value and determine its type
    current_value = getattr(settings, setting_key)
    value_type = type(current_value)

    # Step 4: Ask for a new value
    new_value, ok = QInputDialog.getText(
        parent_widget,
        "Enter New Value",
        f"Current ({value_type.__name__}): {current_value}\nNew Value:"
    )

    if not ok or not new_value:
        return  # User canceled input

    # Step 5: Convert the input to the correct type and update the setting
    try:
        converted_value = convert_value(new_value, value_type)
        set_setting(setting_key, converted_value)
        QMessageBox.information(
            parent_widget,
            "Success",
            f"Setting '{setting_key}' updated to {converted_value}."
        )
    except ValueError:
        QMessageBox.warning(
            parent_widget,
            "Error",
            "Invalid input type. Please enter a valid value."
        )

def set_setting(key, value):
    """Updates a setting with the given key and value."""
    setattr(settings, key, value)

def convert_value(value_str, target_type):
    """Converts a string value to the specified target type."""
    if target_type == int:
        return int(value_str)
    elif target_type == float:
        return float(value_str)
    elif target_type == bool:
        return value_str.lower() in ['true', '1', 'yes']
    elif target_type == list:
        # Assuming comma-separated values
        return value_str.split(",")
    else:
        return str(value_str)  # Default to string

def reload_settings():
    """Reloads the settings module."""
    if "settings" in sys.modules:
        del sys.modules["settings"]
    import settings
    importlib.reload(settings)  # Reload the settings module
    print("Settings reloaded:", settings.__dict__)  # Debugging output
    print("Reloaded settings")