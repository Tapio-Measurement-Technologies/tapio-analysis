from PyQt6.QtWidgets import QMenu, QLineEdit
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.text import Text, Annotation
import matplotlib.text as mtext
from functools import wraps
from utils.types import PlotAnnotation

def check_axes(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.figure.axes:
            return
        return func(self, *args, **kwargs)
    return wrapper

class DraggableAnnotation:
    def __init__(self, annotation):
        self.annotation: Annotation | Text = annotation
        self.draggable = False
        self.offset = (0, 0)

class AnnotableCanvas(FigureCanvasQTAgg):
    def __init__(self, figure=None, parent=None):
        if figure is None:
            figure = Figure()
        super().__init__(figure)
        self.setParent(parent)
        self.ax = self.figure.add_subplot(111)

        self.annotations: list[DraggableAnnotation] = []
        self.selected_annotation: DraggableAnnotation | None = None
        self.editing_annotation: DraggableAnnotation | None = None
        self.editor = None

        self.mpl_connect('pick_event', self.on_pick)
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('button_release_event', self.on_release)
        self.mpl_connect('motion_notify_event', self.on_motion)

    @check_axes
    def add_annotation(self, annotation: PlotAnnotation):
        ax = None
        if annotation.axes_index is not None and annotation.axes_index < len(self.figure.axes):
            ax = self.figure.axes[annotation.axes_index]
        else:
            # Fallback for old annotations or single-plot figures
            ax = self.figure.axes[0]

        if annotation.arrowprops:
            ax_annotation = ax.annotate(annotation.text,
                                        xy=annotation.xy,
                                        xytext=annotation.xytext,
                                        arrowprops=annotation.arrowprops,
                                        picker=True,
                                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1, alpha=0.7),
                                        **annotation.style)
        else:
            ax_annotation = ax.text(annotation.xy[0], annotation.xy[1], annotation.text,
                                    picker=True,
                                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=1, alpha=0.7),
                                    **annotation.style)

        draggable_annotation = DraggableAnnotation(ax_annotation)
        self.annotations.append(draggable_annotation)
        self.draw()

    @check_axes
    def on_pick(self, event):
        if isinstance(event.artist, mtext.Text):
            for annotation in self.annotations:
                if event.artist == annotation.annotation:
                    self.selected_annotation = annotation
                    self.selected_annotation.draggable = True
                    # Calculate offset from click to annotation position
                    mouse_event = event.mouseevent
                    x, y = annotation.annotation.get_position()
                    self.selected_annotation.offset = (x - mouse_event.xdata, y - mouse_event.ydata)
                    break

    @check_axes
    def on_press(self, event):
        # Check for an ongoing edit
        if self.editor and not self.editor.geometry().contains(event.guiEvent.pos()):
            self.finish_editing()
            return

        if event.button == 1 and event.dblclick:
            if event.xdata is None or event.ydata is None:
                return

            # Check if an annotation was double-clicked
            clicked_annotation = None
            for ann in self.annotations:
                contains, _ = ann.annotation.contains(event)
                if contains:
                    clicked_annotation = ann
                    break

            if clicked_annotation:
                self.edit_annotation(clicked_annotation)
                return

        if event.button == 3:  # Right-click
            if event.xdata is None or event.ydata is None:
                return

            # Check if an annotation was clicked
            clicked_annotation = None
            for ann in self.annotations:
                contains, _ = ann.annotation.contains(event)
                if contains:
                    clicked_annotation = ann
                    break

            if clicked_annotation:
                self._show_remove_context_menu(event, clicked_annotation)
            else:
                self._show_add_context_menu(event)
            return

    def edit_annotation(self, annotation_to_edit: DraggableAnnotation):
        if self.editor:
            self.finish_editing()

        self.editing_annotation = annotation_to_edit
        bbox = self.editing_annotation.annotation.get_bbox_patch().get_window_extent()

        # Invert y-coordinate for Qt
        x, y = bbox.x0, self.height() - bbox.y1

        self.editor = QLineEdit(self)
        self.editor.setText(self.editing_annotation.annotation.get_text())
        self.editor.setGeometry(int(x), int(y), int(bbox.width), int(bbox.height))

        self.editor.editingFinished.connect(self.finish_editing)
        self.editor.show()
        self.editor.setFocus()

    def finish_editing(self):
        if self.editor:
            new_text = self.editor.text()
            self.editing_annotation.annotation.set_text(new_text)

            self.editor.deleteLater()
            self.editor = None
            self.editing_annotation = None
            self.draw_idle()

    def _show_add_context_menu(self, event):
        menu = QMenu(self)
        add_text_action = menu.addAction("Add Text Label")
        add_arrow_action = menu.addAction("Add Arrow")

        action = menu.exec(self.mapToGlobal(event.guiEvent.pos()))

        if not hasattr(event, 'inaxes') or event.inaxes not in self.figure.axes:
            return

        axes_index = self.figure.axes.index(event.inaxes)

        if action == add_text_action:
            self.add_annotation(PlotAnnotation(
                text=f'Label {len(self.annotations) + 1}',
                xy=(event.xdata, event.ydata),
                axes_index=axes_index
            ))
        elif action == add_arrow_action:
            ax = self.figure.axes[axes_index]
            x_range = ax.get_xlim()[1] - ax.get_xlim()[0]
            xytext_offset_x = 0.1 * x_range

            if event.xdata + xytext_offset_x > ax.get_xlim()[1]:
                 xytext_x = event.xdata - xytext_offset_x
            else:
                 xytext_x = event.xdata + xytext_offset_x

            self.add_annotation(PlotAnnotation(
                text=f'Arrow {len(self.annotations) + 1}',
                xy=(event.xdata, event.ydata),
                xytext=(xytext_x, event.ydata),
                arrowprops=dict(facecolor='black', shrink=0.05, width=1, headwidth=8),
                axes_index=axes_index
            ))

    def _show_remove_context_menu(self, event, annotation_to_remove: DraggableAnnotation):
        menu = QMenu(self)
        remove_action = menu.addAction("Remove")

        action = menu.exec(self.mapToGlobal(event.guiEvent.pos()))

        if action == remove_action:
            self.remove_annotation(annotation_to_remove)

    def remove_annotation(self, annotation_to_remove: DraggableAnnotation):
        annotation_to_remove.annotation.remove()
        self.annotations.remove(annotation_to_remove)
        if self.selected_annotation == annotation_to_remove:
            self.selected_annotation = None
        self.draw_idle()

    def on_release(self, event):
        if self.selected_annotation:
            self.selected_annotation.draggable = False
            self.selected_annotation = None

    @check_axes
    def on_motion(self, event):
        if self.selected_annotation and self.selected_annotation.draggable:
            if event.xdata is not None and event.ydata is not None:
                dx, dy = self.selected_annotation.offset
                new_x = event.xdata + dx
                new_y = event.ydata + dy
                self.selected_annotation.annotation.set_position((new_x, new_y))
                self.draw_idle()

    def get_annotations(self) -> list[PlotAnnotation]:
        """Returns a serializable list of annotations."""
        plot_annotations = []
        for ann in self.annotations:
            if ann.annotation.get_figure() is not None and ann.annotation.axes in self.figure.axes:
                axes_index = self.figure.axes.index(ann.annotation.axes)
                text = ann.annotation.get_text()
                style = {k: v for k, v in ann.annotation.properties().items() if k in ['color', 'fontsize', 'fontweight']}

                if isinstance(ann.annotation, mtext.Annotation):
                    plot_annotations.append(PlotAnnotation(
                        text=text,
                        xy=ann.annotation.xy,
                        xytext=ann.annotation.get_position(),
                        arrowprops=ann.annotation.arrowprops,
                        style=style,
                        axes_index=axes_index
                    ))
                else:
                    plot_annotations.append(PlotAnnotation(
                        text=text,
                        xy=ann.annotation.get_position(),
                        style=style,
                        axes_index=axes_index
                    ))
        return plot_annotations

    def set_annotations(self, annotations_data: list[PlotAnnotation]):
        """Clears existing annotations and adds new ones from data."""
        for ann in self.annotations:
            ann.annotation.remove()
        self.annotations.clear()
        self.selected_annotation = None

        if not self.figure.axes:
            return

        for ann_data in annotations_data:
            self.add_annotation(ann_data)

        self.draw_idle()

