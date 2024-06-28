from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QMenuBar, QGridLayout
from PyQt6.QtGui import QAction
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from qtpy.QtCore import Qt
import numpy as np
from utils.data_loader import DataMixin

from gui.components import AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin
from controllers import VCAController


class VCAWindow(QWidget, DataMixin, AnalysisRangeMixin, ChannelMixin, BandPassFilterMixin, SampleSelectMixin):
    def __init__(self, controller: VCAController | None = None):
        super().__init__()
        self.dataMixin = DataMixin.getInstance()
        self.controller = controller if controller else VCAController()
        self.initUI()

    def initMenuBar(self, layout):
        menuBar = QMenuBar()
        layout.setMenuBar(menuBar)
        fileMenu = menuBar.addMenu('File')
        viewMenu = menuBar.addMenu('View')

        self.sampleSelectorWindow = None
        self.selectSamplesAction = QAction('Select samples', self)
        viewMenu.addAction(self.selectSamplesAction)
        self.selectSamplesAction.triggered.connect(self.toggleSelectSamples)

    def initUI(self):
        self.setWindowTitle(
            f"Variance component analysis ({self.dataMixin.measurement_label})")
        self.setGeometry(100, 100, 800, 850)

        mainLayout = QVBoxLayout()
        self.setLayout(mainLayout)
        self.initMenuBar(mainLayout)
        # Add the channel selector
        self.addChannelSelector(mainLayout)

        # Analysis range slider
        self.addAnalysisRangeSlider(mainLayout)

        self.addBandPassRangeSlider(mainLayout)
        # Add statistics labels
        statsLayout = QGridLayout()
        self.total_std_dev_text = QLabel("Total standard deviation")
        self.md_std_dev_text = QLabel("MD standard deviation")
        self.cd_std_dev_text = QLabel("CD Standard deviation ")
        self.residual_std_dev_text = QLabel("Residual standard deviation")
        self.unit_label = QLabel("Unit")
        self.p_label = QLabel("% of mean")

        self.total_std_dev_label = QLabel("1")
        self.md_std_dev_label = QLabel("2")
        self.cd_std_dev_label = QLabel("3")
        self.residual_std_dev_label = QLabel("4")

        self.total_std_dev_p_label = QLabel("5")
        self.md_std_dev_p_label = QLabel("6")
        self.cd_std_dev_p_label = QLabel("7")
        self.residual_std_dev_p_label = QLabel("8")

        statsLayout.addWidget(self.unit_label, 0, 1)
        statsLayout.addWidget(self.p_label, 0, 2)

        statsLayout.addWidget(self.total_std_dev_text, 1, 0)
        statsLayout.addWidget(self.md_std_dev_text, 2, 0)
        statsLayout.addWidget(self.cd_std_dev_text, 3, 0)
        statsLayout.addWidget(self.residual_std_dev_text, 4, 0)

        statsLayout.addWidget(self.total_std_dev_label, 1, 1)
        statsLayout.addWidget(self.md_std_dev_label, 2, 1)
        statsLayout.addWidget(self.cd_std_dev_label, 3, 1)
        statsLayout.addWidget(self.residual_std_dev_label, 4, 1)

        statsLayout.addWidget(self.total_std_dev_p_label, 1, 2)
        statsLayout.addWidget(self.md_std_dev_p_label, 2, 2)
        statsLayout.addWidget(self.cd_std_dev_p_label, 3, 2)
        statsLayout.addWidget(self.residual_std_dev_p_label, 4, 2)


        mainLayout.addLayout(statsLayout)

        for label in [self.total_std_dev_label, self.md_std_dev_label, self.cd_std_dev_label, self.residual_std_dev_label]:
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Now add a stretch factor before adding the figure canvas to give it priority to expand
        # mainLayout.addStretch(1)

        self.plot = self.controller.getCanvas()
        # Add with stretch factor to allow expansion
        mainLayout.addWidget(self.plot, 1)
        self.toolbar = NavigationToolbar(self.plot, self)
        mainLayout.addWidget(self.toolbar)

        self.refresh()

    def refresh_widgets(self):
        self.initAnalysisRangeSlider(block_signals=True)
        self.initBandPassRangeSlider(block_signals=True)
        self.initChannelSelector(block_signals=True)

    def refresh(self):
        self.controller.updatePlot()
        self.refresh_widgets()
        self.updateVCAStatistics(self.controller.filtered_data)

    def updateVCAStatistics(self, data):

        vca_stats = {}
        data = np.array(data)
        total, md, cd, res = self.controller.calculate_variances(data)
        vca_stats["md_std_dev"] = np.sqrt(md)
        vca_stats["cd_std_dev"] = np.sqrt(cd)
        vca_stats["total_std_dev"] = np.sqrt(total)
        vca_stats["residual_std_dev"] = np.sqrt(res)

        mean = np.mean(data)

        vca_stats["md_std_dev_p"] = 100 * vca_stats["md_std_dev"] / mean
        vca_stats["cd_std_dev_p"] = 100 * vca_stats["cd_std_dev"] / mean
        vca_stats["total_std_dev_p"] = 100 * vca_stats["total_std_dev"] / mean
        vca_stats["residual_std_dev_p"] = 100 * \
            vca_stats["residual_std_dev"] / mean


        self.unit_label.setText(f"{self.dataMixin.units[self.controller.channel]}")
        self.total_std_dev_label.setText(f"{vca_stats['total_std_dev']:.2f}")
        self.md_std_dev_label.setText(f"{vca_stats['md_std_dev']:.2f}")
        self.cd_std_dev_label.setText(f"{vca_stats['cd_std_dev']:.2f}")
        self.residual_std_dev_label.setText(f"{vca_stats['residual_std_dev']:.2f}")

        self.total_std_dev_p_label.setText(f"{vca_stats['total_std_dev_p']:.2f}")
        self.md_std_dev_p_label.setText(f"{vca_stats['md_std_dev_p']:.2f}")
        self.cd_std_dev_p_label.setText(f"{vca_stats['cd_std_dev_p']:.2f}")
        self.residual_std_dev_p_label.setText(f"{vca_stats['residual_std_dev_p']:.2f}")
