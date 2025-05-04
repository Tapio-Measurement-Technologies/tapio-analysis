from gui.cd_profile import CDProfileWindow
from gui.channel_correlation import ChannelCorrelationWindow
from gui.correlation_matrix import CorrelationMatrixWindow
from gui.formation import FormationWindow
from gui.spectrum import SpectrumWindow
from gui.cepstrum import CepstrumWindow
from gui.coherence import CoherenceWindow
from gui.spectrogram import SpectrogramWindow
from gui.time_domain import TimeDomainWindow
from gui.vca import VCAWindow
from gui.log_window import LogWindow

def openTimeDomainAnalysis(parent, controller = None):
    newWindow = TimeDomainWindow(controller)
    parent.add_window(newWindow)

def openVCA(parent, controller = None):
    newWindow = VCAWindow(controller)
    parent.add_window(newWindow)

def openCDProfileAnalysis(parent, window_type="2d", controller = None):
    newWindow = CDProfileWindow(window_type, controller)
    parent.add_window(newWindow)

def openSpectrumAnalysis(parent, window_type="MD", controller = None):
    newWindow = SpectrumWindow(window_type, controller)
    parent.add_window(newWindow)

def openCepstrumAnalysis(parent, window_type="MD", controller = None):
    newWindow = CepstrumWindow(window_type, controller)
    parent.add_window(newWindow)

def openCoherenceAnalysis(parent, window_type="MD", controller = None):
    newWindow = CoherenceWindow(window_type, controller)
    parent.add_window(newWindow)



def openSpectroGram(parent, window_type="MD", controller = None):
    newWindow = SpectrogramWindow(window_type, controller)
    parent.add_window(newWindow)

def openCorrelationMatrix(parent, window_type="MD", controller = None):
    newWindow = CorrelationMatrixWindow(window_type, controller)
    parent.add_window(newWindow)

def openChannelCorrelation(parent, window_type="MD", controller = None):
    newWindow = ChannelCorrelationWindow(window_type, controller)
    parent.add_window(newWindow)

def openFormationAnalysis(parent, window_type="MD", controller = None):
    newWindow = FormationWindow(window_type, controller)
    parent.add_window(newWindow)

def openLogWindow(log_manager):
    newWindow = LogWindow(log_manager)
    newWindow.show()
    return newWindow