# frontend/src/ui/overlay.py

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont


class StealthOverlay(QWidget):
    """
    Always-on-top, transparent overlay that displays AI-generated answers.
    Uses a Qt signal to safely update from worker threads.
    """
    # Signal to receive new answer text from any thread
    answerReady = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        # Connect the signal to the slot that updates the label and shows the window
        self.answerReady.connect(self._on_answer_ready)

    def _init_ui(self) -> None:
        # Window flags: always on top, frameless, tool window (no taskbar icon)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        # Make background transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Styling: semi‐transparent dark background, rounded corners
        self.setStyleSheet("""
            QWidget { background-color: rgba(0, 0, 0, 160); border-radius: 8px; }
            QLabel  { color: white; padding: 10px; }
        """)
        # Default size and position (user can drag later)
        self.resize(400, 150)

        # Label to show the answer text
        self.label = QLabel("AI Assistant Ready...", self)
        self.label.setWordWrap(True)
        self.label.setFont(QFont("Arial", 12))

        # Layout
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self.setLayout(layout)

    @pyqtSlot(str)
    def _on_answer_ready(self, text: str) -> None:
        """
        Slot invoked via answerReady signal in the GUI thread.
        Updates the label text and shows the overlay.
        """
        self.label.setText(text)
        self.show()

    def toggle_visibility(self) -> None:
        """
        Hotkey can call this to show/hide the overlay.
        Always executed in the GUI thread.
        """
        self.setVisible(not self.isVisible())




