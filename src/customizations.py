from matplotlib.figure import Figure
import importlib


def apply_plot_customizations(figure: Figure):
    # Set the aspect ratio to 5:1 (width:height)
    has_title = False

    # Check if any of the axes have a title
    for ax in figure.axes:
        if ax.get_title():
            has_title = True
            break  # No need to check further once a title is found

    if has_title:
        aspect_ratio = 2 / 1  # 5:1 ratio

        # Get current figure dimensions (inches)
        width, height = figure.get_size_inches()

        # Set the new figure size while maintaining the 5:1 ratio
        new_width = height * aspect_ratio  # adjust width based on current height
        figure.set_size_inches(new_width, height*0.9)
        figure.tight_layout()


try:
    local_customizations = importlib.import_module("local_customizations")
    if hasattr(local_customizations, "apply_plot_customizations"):
        apply_plot_customizations = local_customizations.apply_plot_customizations
except ModuleNotFoundError:
    # local_customizations.py does not exist, continue with the default function
    pass
