# Tapio Analysis
# Copyright 2024 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Global store for application-wide resources and objects.
This helps avoid circular imports by providing a central place to access shared resources.
"""
from utils.logging import LogManager
from utils.dynamic_loader import load_modules_from_folder
import os
from settings import ANALYSIS_DIR, LOADERS_DIR, EXPORTERS_DIR
from utils.types import ExporterModule, ModuleName, LoaderModule
from utils.analysis import AnalysisModule
from utils.measurement import Measurement
from typing import cast
from PyQt6.QtWidgets import QWidget

# This will be set in main.py
log_manager: LogManager | None = None
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

loaders: dict[ModuleName, LoaderModule] = {
    module_name: cast(LoaderModule, module)
    for module_name, module in load_modules_from_folder(os.path.join(base_path, LOADERS_DIR)).items()
}

exporters: dict[ModuleName, ExporterModule] = {
    module_name: cast(ExporterModule, module)
    for module_name, module in load_modules_from_folder(os.path.join(base_path, EXPORTERS_DIR)).items()
}

analyses: dict[ModuleName, AnalysisModule] = {
    module_name: AnalysisModule(
        analysis_name=module.analysis_name,
        analysis_types=module.analysis_types,
        AnalysisController=module.AnalysisController,
        AnalysisWindow=module.AnalysisWindow,
        allow_multiple_instances=getattr(module, "allow_multiple_instances", True)
    )
    for module_name, module in load_modules_from_folder(os.path.join(base_path, ANALYSIS_DIR)).items()
}

loaded_measurement: Measurement | None = None
open_windows: list[QWidget] = []