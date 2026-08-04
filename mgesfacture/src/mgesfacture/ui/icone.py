"""Icône ronde verte de l'application, générée par dessin (pas de fichier
image externe à maintenir)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def icone_ronde_verte(taille: int = 64) -> QIcon:
    pixmap = QPixmap(taille, taille)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#2e7d32"))
    marge = taille * 0.05
    painter.drawEllipse(QRectF(marge, marge, taille - 2 * marge, taille - 2 * marge))
    painter.end()

    return QIcon(pixmap)
