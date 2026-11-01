"""Shared label outline, drawn in one retained scene item."""
from math import hypot, log2
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsPathItem
from ..class_colors import PALETTE


LABEL_RED = PALETTE[0].lower()


def outline_metrics(scale, screen_extent, selected=False):
    """Return logical screen pixels, independent of image pixels and display DPI."""
    zoom = max(-3.0, min(3.0, log2(max(scale, 1e-9))))
    width = 1.7 + zoom * .15 + (.6 if selected else 0)
    dash = min(7.0 + zoom, max(2.5, screen_extent / 10.0))
    return width, dash, dash * .65


class LabelItem(QGraphicsPathItem):
    highlighted=False
    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        transform = painter.worldTransform()
        scale = hypot(transform.m11(), transform.m12())
        bounds = self.path().boundingRect()
        selected = self.highlighted
        width, dash, gap = outline_metrics(scale, max(bounds.width(), bounds.height()) * scale, selected)
        backing = QPen(QColor('white'), width + 2)
        backing.setCosmetic(True)
        painter.setPen(backing)
        painter.drawPath(self.path())
        outline = QPen(self.pen().color(), width, Qt.PenStyle.DashLine)
        outline.setCosmetic(True)
        # Qt expresses dash entries in pen-width units, not screen pixels.
        outline.setDashPattern([dash / width, gap / width])
        painter.setPen(outline)
        painter.drawPath(self.path())
        painter.restore()
