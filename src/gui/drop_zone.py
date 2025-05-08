# Tapio Analysis
# Copyright 2025 Tapio Measurement Technologies Oy

# Tapio Analysis is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QHBoxLayout, QStackedWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QCursor
from utils.measurement import MeasurementFileType


class DropZoneWidget(QWidget):
    """Widget that accepts file drops and emits a signal with the file paths."""

    filesDropped = pyqtSignal(list)
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        # Set up the UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create a stacked widget to switch between file labels and drop zone
        self.stackedWidget = QStackedWidget()

        # Create the drop zone widget
        self.dropZoneWidget = QWidget()
        dropZoneLayout = QVBoxLayout(self.dropZoneWidget)

        self.dropLabel = QLabel("Drop files here or click to browse")
        self.dropLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setNormalStyle(self.dropLabel)

        dropZoneLayout.addWidget(self.dropLabel)

        # Create the file labels widget
        self.fileLabelsWidget = QWidget()
        self.fileLabelsLayout = QVBoxLayout(self.fileLabelsWidget)
        self.fileLabels = {}

        # Set normal style for file labels widget
        self.setNormalStyleFileLabels(self.fileLabelsWidget)

        # Add both widgets to the stack
        self.stackedWidget.addWidget(self.fileLabelsWidget)
        self.stackedWidget.addWidget(self.dropZoneWidget)

        layout.addWidget(self.stackedWidget)
        self.setLayout(layout)

        # Make the widget look clickable
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        # Default to drop zone view
        self.showDropZone()

        # Track hover state
        self.isHovering = False

    def setNormalStyle(self, label):
        """Set the normal style for the drop zone."""
        label.setStyleSheet("""
            font-size: 16px;
            color: #666;
            padding: 20px;
            border: 2px dashed #aaa;
            border-radius: 8px;
            background-color: #f8f8f8;
        """)

    def setHoverStyle(self, label):
        """Set the hover/active style for the drop zone."""
        label.setStyleSheet("""
            font-size: 16px;
            color: #333;
            padding: 20px;
            border: 2px dashed #3498db;
            border-radius: 8px;
            background-color: #e8f4fc;
        """)

    def setNormalStyleFileLabels(self, widget):
        """Set the normal style for the file labels widget."""
        widget.setStyleSheet("""
            background-color: transparent;
            border-radius: 8px;
        """)

    def setHoverStyleFileLabels(self, widget):
        """Set the hover style for the file labels widget."""
        widget.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.05);
            border-radius: 8px;
        """)

    def setupFileLabels(self, measurement=None):
        """Set up file labels based on the measurement."""
        # Clear existing labels
        while self.fileLabelsLayout.count():
            item = self.fileLabelsLayout.takeAt(0)
            if item.layout():
                while item.layout().count():
                    subitem = item.layout().takeAt(0)
                    if subitem.widget():
                        subitem.widget().deleteLater()
                item.layout().deleteLater()
            elif item.widget():
                item.widget().deleteLater()

        self.fileLabels = {}

        # Add file labels for each file type
        for fileType in MeasurementFileType:
            # Create file picker layout
            fileLayout = QHBoxLayout()
            fileLabel = QLabel(f"{fileType.value} file:")
            self.fileLabels[fileType] = QLabel("No file selected")

            # Ensure labels don't inherit hover effects
            fileLabel.setStyleSheet("background-color: transparent;")
            self.fileLabels[fileType].setStyleSheet("background-color: transparent;")

            fileLayout.addWidget(fileLabel)
            fileLayout.addWidget(self.fileLabels[fileType])
            self.fileLabelsLayout.addLayout(fileLayout)

        # Add stretch to push everything to the top
        self.fileLabelsLayout.addStretch(1)

        # Update file labels if measurement is provided
        if measurement:
            self.updateFileLabels(measurement)

    def updateFileLabels(self, measurement):
        """Update file labels with file paths from the measurement."""
        for fileType, label in self.fileLabels.items():
            file_path = measurement.get_file_path(fileType)
            label_text = file_path.split('/')[-1] if file_path else "No file selected"
            label.setText(label_text)

    def showFileLabels(self, measurement=None):
        """Show file labels and update them with the measurement."""
        self.setupFileLabels(measurement)
        self.stackedWidget.setCurrentIndex(0)
        # Reset to normal style when switching views
        self.setNormalStyleFileLabels(self.fileLabelsWidget)

    def showDropZone(self):
        """Show the drop zone."""
        self.stackedWidget.setCurrentIndex(1)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events to accept file drops."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if self.stackedWidget.currentIndex() == 1:  # Drop zone view
                self.setHoverStyle(self.dropLabel)
            else:  # File labels view
                self.setHoverStyleFileLabels(self.fileLabelsWidget)

    def dragLeaveEvent(self, event):
        """Reset styling when drag leaves the widget."""
        if self.stackedWidget.currentIndex() == 1:  # Drop zone view
            self.setNormalStyle(self.dropLabel)
        else:  # File labels view
            self.setNormalStyleFileLabels(self.fileLabelsWidget)

    def dropEvent(self, event: QDropEvent):
        """Handle file drop events."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

            # Reset styling
            if self.stackedWidget.currentIndex() == 1:  # Drop zone view
                self.setNormalStyle(self.dropLabel)
            else:  # File labels view
                self.setNormalStyleFileLabels(self.fileLabelsWidget)

            # Get file paths from the drop event
            file_paths = []
            for url in event.mimeData().urls():
                file_paths.append(url.toLocalFile())

            # Emit signal with file paths
            self.filesDropped.emit(file_paths)

    def enterEvent(self, event):
        """Handle mouse enter events to show hover style."""
        self.isHovering = True
        if self.stackedWidget.currentIndex() == 1:  # Drop zone view
            self.setHoverStyle(self.dropLabel)
        else:  # File labels view
            self.setHoverStyleFileLabels(self.fileLabelsWidget)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave events to reset style."""
        self.isHovering = False
        if self.stackedWidget.currentIndex() == 1:  # Drop zone view
            self.setNormalStyle(self.dropLabel)
        else:  # File labels view
            self.setNormalStyleFileLabels(self.fileLabelsWidget)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press events to show hover style."""
        if self.stackedWidget.currentIndex() == 1:  # Drop zone view
            self.setHoverStyle(self.dropLabel)
        else:  # File labels view
            self.setHoverStyleFileLabels(self.fileLabelsWidget)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release events to emit clicked signal."""
        if self.isHovering:
            if self.stackedWidget.currentIndex() == 1:  # Drop zone view
                self.setHoverStyle(self.dropLabel)
            else:  # File labels view
                self.setHoverStyleFileLabels(self.fileLabelsWidget)
        else:
            if self.stackedWidget.currentIndex() == 1:  # Drop zone view
                self.setNormalStyle(self.dropLabel)
            else:  # File labels view
                self.setNormalStyleFileLabels(self.fileLabelsWidget)
        self.clicked.emit()
        super().mouseReleaseEvent(event)