"""Stable raster rows with a reserved right readiness indicator."""
from PySide6.QtCore import Qt, QRectF, QObject, QEvent, QVariantAnimation, QEasingCurve,QPersistentModelIndex,QSize
from PySide6.QtGui import QColor, QPalette, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QAbstractItemView, QLayout,QSizePolicy


class RasterListSizer(QObject):
    """Let native layouts fit the list around cards and wrapped metadata."""
    minimum_height=72

    def __init__(self,view,scroll):
        super().__init__(view);self.view=view;self.scroll=scroll
        view.setMinimumHeight(self.minimum_height)
        view.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        view.setUniformItemSizes(True)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

    def settle(self):
        """A project transition must capture the final layout, without a later jump."""
        root=self.scroll.widget()
        # Flush metadata/card size caches before a project transition captures
        # the frame. Normal resizing is handled by the layouts themselves.
        for layout in reversed(root.findChildren(QLayout)):
            layout.invalidate();layout.activate()


class RasterItemDelegate(QStyledItemDelegate):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.hovered=QPersistentModelIndex()
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.viewport().installEventFilter(self)
        self.revealing={};self.reveal_time=0.;self.reveal_curve=QEasingCurve(QEasingCurve.Type.OutCubic)
        self.reveal_animation=QVariantAnimation(self)
        self.reveal_animation.valueChanged.connect(self._advance_reveal)
        self.reveal_animation.finished.connect(self._finish_reveal)

    def reveal(self,identifiers):
        if not identifiers or not self.view.isVisible():return
        self._finish_reveal()
        # Cap the stagger so even a VRT with thousands of tiles finishes in
        # under a quarter second. No per-row timers or model writes per frame.
        self.revealing={identifier:min(i,5)*12 for i,identifier in enumerate(identifiers)}
        duration=180+min(len(identifiers)-1,5)*12;self.reveal_time=0.
        self.reveal_animation.setDuration(duration)
        self.reveal_animation.setStartValue(0.);self.reveal_animation.setEndValue(float(duration));self.reveal_animation.start()

    def _advance_reveal(self,value):
        self.reveal_time=float(value);self.view.viewport().update()

    def _finish_reveal(self):
        self.reveal_animation.stop();self.revealing.clear();self.view.viewport().update()

    def sizeHint(self,option,index):
        # Names never determine horizontal content width; the indicator stays
        # pinned while the painter elides text to the viewport's available space.
        return QSize(0,super().sizeHint(option,index).height())

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Hide:self._finish_reveal()
        if event.type() in (QEvent.Type.MouseMove,QEvent.Type.Leave):
            index=QPersistentModelIndex(self.view.indexAt(event.position().toPoint())) if event.type()==QEvent.Type.MouseMove else QPersistentModelIndex()
            if index!=self.hovered:
                old=self.hovered;self.hovered=index
                for item in (old,index):
                    if item.isValid():self.view.viewport().update(self.view.visualRect(item))
        return False

    def paint(self, painter, option, index):
        from .raster_presenter import IDENTIFIER_ROLE
        painter.save()
        delay=self.revealing.get(index.data(IDENTIFIER_ROLE))
        if delay is not None:
            progress=max(0.,min(1.,(self.reveal_time-delay)/180.))
            painter.setOpacity(painter.opacity()*self.reveal_curve.valueForProgress(progress))
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if index==self.hovered:opt.state|=QStyle.StateFlag.State_MouseOver
        else:opt.state&=~QStyle.StateFlag.State_MouseOver
        text = opt.text
        ready = bool(index.data(Qt.ItemDataRole.UserRole))
        opt.text = ''
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        text_rect = opt.rect.adjusted(10, 0, -32, 0)
        role = QPalette.ColorRole.HighlightedText if opt.state & QStyle.StateFlag.State_Selected else QPalette.ColorRole.Text
        painter.setFont(opt.font)
        painter.setPen(opt.palette.color(role))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         opt.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, text_rect.width())))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        x,y=opt.rect.right()-17,opt.rect.center().y()
        painter.setPen(Qt.PenStyle.NoPen if ready else QPen(QColor('#b5c9cf'),1.2))
        painter.setBrush(QColor('#087f83') if ready else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(x-7,y-7,14,14))
        if ready:
            painter.setPen(QPen(QColor('white'), 1.7, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath()
            path.moveTo(x - 3.5, y)
            path.lineTo(x - 1, y + 2.5)
            path.lineTo(x + 3.5, y - 3)
            painter.drawPath(path)
        painter.restore()
