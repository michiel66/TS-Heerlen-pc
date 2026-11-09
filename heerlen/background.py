"""Simple preset and user-image wallpapers for the desktop window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from heerlen.storage import settings_path

BACKGROUNDS = {
    "Nachtblauw": ("#030c1b", "#10345c"),
    "Radio groen": ("#031b1b", "#0a4d40"),
    "Neon paars": ("#120e2c", "#492a7a"),
    "Zwart": ("#030303", "#181818"),
    "Eigen afbeelding": ("#030c1b", "#10345c"),
}


class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preset = "Nachtblauw"
        self.wallpaper = QPixmap()

    def set_preset(self, preset: str):
        self.preset = preset if preset in BACKGROUNDS else "Nachtblauw"
        self.wallpaper = QPixmap()
        if self.preset == "Eigen afbeelding":
            self.wallpaper.load(str(settings_path().parent / "wallpaper.png"))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        first, second = BACKGROUNDS.get(self.preset, BACKGROUNDS["Nachtblauw"])
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(first))
        gradient.setColorAt(1, QColor(second))
        painter.fillRect(self.rect(), gradient)
        if not self.wallpaper.isNull():
            # Crop to fit rather than distort the uploaded image.
            scaled = self.wallpaper.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
            painter.fillRect(self.rect(), QColor(0, 10, 23, 125))
        super().paintEvent(event)


def store_wallpaper(path: str) -> None:
    """Limit the size/dimensions before making an app-local copy."""
    image_path = Path(path)
    if image_path.stat().st_size > 20_000_000:
        raise ValueError("Kies een afbeelding kleiner dan 20 MB.")
    original = QPixmap(path)
    if original.isNull():
        raise ValueError("De afbeelding kon niet worden geopend.")
    scaled = original.scaled(
        1920, 1080, Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    dest = settings_path().parent / "wallpaper.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not scaled.save(str(dest), "PNG"):
        raise OSError("Kon de afbeelding niet in de app-instellingen opslaan.")
