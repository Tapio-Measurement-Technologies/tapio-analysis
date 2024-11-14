from matplotlib.figure import Figure
import importlib


def apply_plot_customizations(figure: Figure):
    pass


try:
    local_customizations = importlib.import_module("local_customizations")
    if hasattr(local_customizations, "apply_plot_customizations"):
        apply_plot_customizations = local_customizations.apply_plot_customizations
except ModuleNotFoundError:
    # local_customizations.py does not exist, continue with the default function
    pass
