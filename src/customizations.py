
from matplotlib.figure import Figure

def apply_plot_customizations(analysis_widget):
    figure = analysis_widget.controller.figure
    apply_black_and_white(figure)
    if analysis_widget.analysis_name not in ["Variance component analysis", "CD Profile waterfall"]:
        set_figure_height(figure, 2)
    # Ensure the figure canvas is redrawn with the new settings
    figure.canvas.draw()

def apply_black_and_white(figure: Figure):
    """
    Apply black and white (grayscale) coloring to a matplotlib figure.

    Parameters:
    fig (matplotlib.figure.Figure): The matplotlib figure to apply the black and white coloring to.
    """
    # Iterate through all axes in the figure
    for ax in figure.get_axes():
        # Iterate through all collections in the axes (such as scatter plots)
        for collection in ax.collections:
            collection.set_cmap('gray')

        # Iterate through all images in the axes (such as imshow)
        for image in ax.images:
            image.set_cmap('gray')

        # Iterate through all lines in the axes
        for line in ax.get_lines():
            line.set_color('black')

        # Iterate through all patches in the axes (such as bar plots)
        for patch in ax.patches:
            patch.set_facecolor('black')
            patch.set_edgecolor('black')

        # Set the axis and label colors to black
        ax.spines['bottom'].set_color('black')
        ax.spines['top'].set_color('black')
        ax.spines['right'].set_color('black')
        ax.spines['left'].set_color('black')
        ax.xaxis.label.set_color('black')
        ax.yaxis.label.set_color('black')
        ax.tick_params(axis='x', colors='black')
        ax.tick_params(axis='y', colors='black')

        # Set the title color to black
        ax.title.set_color('black')

def set_figure_height(figure: Figure, new_height):
    figure.set_figheight(new_height)
