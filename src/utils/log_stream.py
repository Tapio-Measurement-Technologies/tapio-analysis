from PyQt6.QtCore import QObject, pyqtSignal
import sys
from enum import Enum

class EmittingStreamType(Enum):
    STDOUT = 'stdout'
    STDERR = 'stderr'

class EmittingStream(QObject):
    textWritten = pyqtSignal(str)
    original_stream = None

    def __init__(self, stream_type: EmittingStreamType):
        super().__init__()
        self.original_stream = getattr(sys, stream_type.value)
        setattr(sys, stream_type.value, self)

    def write(self, text):
        self.textWritten.emit(str(text))
        # Tee into the original stream
        if self.original_stream is not None:
            self.original_stream.write(text)

    def flush(self):
        pass  # Needed for compatibility