"""Dock widget for Ekonomiska kartan."""
from qgis.PyQt.QtWidgets import QDockWidget, QLabel, QVBoxLayout, QWidget


class EkonomiskaKartanDockWidget(QDockWidget):
    """Minimal code-only dock widget (no .ui file, so no uic differences Qt5/Qt6)."""

    def __init__(self, parent=None):
        super().__init__("Ekonomiska kartan", parent)
        self.setObjectName("EkonomiskaKartanDockWidget")

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Hello from Ekonomiska kartan!"))
        layout.addStretch()
        self.setWidget(content)
