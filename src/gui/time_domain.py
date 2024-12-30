from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QMenuBar
from PyQt6.QtGui import QImage
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, StatsMixin, ShowUnfilteredMixin, ShowTimeLabelsMixin, MachineSpeedMixin
from controllers import TimeDomainController
from io import BytesIO

class TimeDomainWindow(QWidget, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, StatsMixin,
                       ShowUnfilteredMixin, ShowTimeLabelsMixin, MachineSpeedMixin):

    def __init__(self, controller: TimeDomainController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else TimeDomainController()
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)

        fileMenu = menuBar.addMenu('File')

        exportAction = self.controller.initExportAction(self, "Export current data")
        fileMenu.addAction(exportAction)

    def initUI(self):
        self.setWindowTitle(f"Time domain analysis ({self.controller.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 700, 800)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)

        # Add the channel selector
        self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)
        self.addBandPassRangeSlider(mainLayout)
        self.addMachineSpeedSpinner(mainLayout)
        self.addShowTimeLabelsCheckbox(mainLayout)
        self.addShowUnfilteredCheckbox(mainLayout)

        # Add statistics labels
        statsLayout = QVBoxLayout()
        self.meanLabel = QLabel("Mean: ")
        self.stdLabel = QLabel("σ: ")
        self.minLabel = QLabel("Min: ")
        self.maxLabel = QLabel("Max: ")

        for label in [self.meanLabel, self.stdLabel, self.minLabel, self.maxLabel]:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            statsLayout.addWidget(label)
        mainLayout.addLayout(statsLayout)

        # Matplotlib figure and canvas
        self.plot = self.controller.getCanvas()
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)
        self.initShowUnfilteredCheckbox(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.updateStatistics(self.controller.data)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            self.copyPlotToClipboard()

    def copyPlotToClipboard(self):
        print("Plot copied to clipboard")
        buffer = BytesIO()
        self.plot.figure.savefig(buffer, format='png', dpi=300)
        buffer.seek(0)

        # Convert buffer to QImage
        image = QImage()
        image.loadFromData(buffer.read(), format='PNG')
        buffer.close()

        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setImage(image)
