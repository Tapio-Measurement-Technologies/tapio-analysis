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
            try:
                self.original_stream.write(text)
            except UnicodeEncodeError:
                # The Windows console is usually cp1252, which cannot encode the
                # symbols the analyses use in their labels. Losing a character
                # in the console is fine; raising is not, because these writes
                # happen inside plot() and the failure is reported to the user
                # as "Invalid parameters" with no plot at all.
                encoding = getattr(self.original_stream, "encoding", None) or "ascii"
                self.original_stream.write(
                    text.encode(encoding, errors="replace").decode(encoding, errors="replace"))

    def flush(self):
        pass  # Needed for compatibility