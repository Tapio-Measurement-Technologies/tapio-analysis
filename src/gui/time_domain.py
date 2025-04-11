from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QMenuBar
from PyQt6.QtGui import QImage
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from utils.data_loader import DataMixin
from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, ShowUnfilteredMixin, ShowTimeLabelsMixin, MachineSpeedMixin, CopyPlotMixin, ChildWindowCloseMixin, StatsWidget
from controllers import TimeDomainController
from io import BytesIO
import settings

class TimeDomainWindow(QWidget, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin,
                       ShowUnfilteredMixin, ShowTimeLabelsMixin, MachineSpeedMixin, CopyPlotMixin, ChildWindowCloseMixin):

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
        self.setGeometry(*settings.TIME_DOMAIN_WINDOW_GEOMETRY)

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

        # Add statistics widget
        self.stats_widget = StatsWidget()
        mainLayout.addWidget(self.stats_widget)

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

    def updateStatistics(self, profile_data):
        unit = self.dataMixin.units[self.controller.channel]
        self.stats_widget.update_statistics(profile_data, unit)




