"""Small vector badges and inset details; updates never change status geometry."""
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QEvent
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QTextLayout,QTextOption
from PySide6.QtWidgets import QScrollBar
from .controls import ElidedLabel


TONES={
    'ready':('#147b68','#e3f3ec'), 'busy':('#117e89','#e2f2f4'),
    'warning':('#96671b','#fbefda'), 'error':('#b14d60','#f9e8ed'),
    'idle':('#667f8a','#eaf0f3'),
}


def symbol(painter,rect,name,color):
    painter.save();painter.translate(rect.topLeft());painter.scale(rect.width()/16,rect.height()/16)
    pen=QPen(QColor(color),1.5);pen.setCapStyle(Qt.PenCapStyle.RoundCap);pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen);painter.setBrush(Qt.BrushStyle.NoBrush);path=QPainterPath()
    if name=='check':
        painter.drawEllipse(QRectF(1,1,14,14));path.moveTo(4,8);path.lineTo(7,11);path.lineTo(12,5)
    elif name=='error':
        painter.drawEllipse(QRectF(1,1,14,14));path.moveTo(8,4);path.lineTo(8,9);painter.drawPoint(QPointF(8,12))
    elif name=='pause':
        painter.drawEllipse(QRectF(1,1,14,14));path.moveTo(6,5);path.lineTo(6,11);path.moveTo(10,5);path.lineTo(10,11)
    elif name=='import':
        path.moveTo(8,1);path.lineTo(8,10);path.moveTo(4,6);path.lineTo(8,10);path.lineTo(12,6)
        path.moveTo(2,10);path.lineTo(2,14);path.lineTo(14,14);path.lineTo(14,10)
    elif name=='model':
        path.moveTo(8,1);path.lineTo(14,4.5);path.lineTo(14,11.5);path.lineTo(8,15);path.lineTo(2,11.5);path.lineTo(2,4.5);path.closeSubpath()
        path.moveTo(2,4.5);path.lineTo(8,8);path.lineTo(14,4.5);path.moveTo(8,8);path.lineTo(8,15)
    elif name=='file':
        path.moveTo(9,1);path.lineTo(3,1);path.lineTo(3,15);path.lineTo(13,15);path.lineTo(13,5);path.closeSubpath()
        path.moveTo(9,1);path.lineTo(9,5);path.lineTo(13,5);path.moveTo(6,9);path.lineTo(10,9);path.moveTo(6,12);path.lineTo(10,12)
    elif name=='activity':
        path.moveTo(1,8);path.lineTo(4,8);path.lineTo(6,3);path.lineTo(10,13);path.lineTo(12,8);path.lineTo(15,8)
    else:
        painter.drawEllipse(QRectF(1,1,14,14));path.moveTo(8,7);path.lineTo(8,12);painter.drawPoint(QPointF(8,4))
    painter.drawPath(path);painter.restore()


class StatusBadge(ElidedLabel):
    def __init__(self,text='',parent=None,result=False):
        super().__init__(text,parent);self.result=result

    def paintEvent(self,event):
        if not self.text():return
        tone=self.property('tone') or 'idle';color,background=TONES.get(tone,TONES['idle'])
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(background))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,1,.0,-1),6,6)
        font=self.font();font.setWeight(font.Weight.DemiBold);painter.setFont(font)
        metrics=painter.fontMetrics();text=metrics.elidedText(self.text(),Qt.TextElideMode.ElideRight,max(0,self.width()-27))
        start=max(5,(self.width()-metrics.horizontalAdvance(text)-19)/2)
        name={'ready':'check','warning':'pause','error':'error'}.get(tone,'activity')
        if not self.result:
            kind=self.property('taskKind') or ''
            if kind in ('import','reference_import','project_open','project_recovery'):name='import'
            elif kind in ('model','model_warmup','resource_install'):name='model'
        symbol(painter,QRectF(start,(self.height()-13)/2,13,13),name,color)
        painter.setPen(QColor(color));painter.drawText(QRectF(start+19,0,self.width()-start-23,self.height()),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,text)


class StatusDetail(ElidedLabel):
    textChanged=Signal()
    hoverChanged=Signal(bool)
    def __init__(self,text='',parent=None,notice=False,wrap=False):
        self.notice=notice;self.wrap=wrap;self._layout=None;self._layout_key=None
        super().__init__(text,parent)
        self.scrollbar=QScrollBar(Qt.Orientation.Vertical,self) if wrap else None
        if self.scrollbar:
            self.scrollbar.hide();self.scrollbar.valueChanged.connect(self.update);self.setMouseTracking(True)

    def setText(self,text):
        changed=str(text)!=getattr(self,'_source_text',None)
        super().setText(text)
        if changed:
            self._layout_key=None
            if hasattr(self,'scrollbar') and self.scrollbar:self.scrollbar.setValue(0)
            if hasattr(self,'scrollbar'):self._sync_scrollbar()
            self.textChanged.emit()

    def _text_layout(self,width):
        width=max(1,int(width));key=(self.text(),width,self.font().toString())
        if key==self._layout_key:return self._layout
        # QTextLayout treats paragraph separators as line breaks; a bare '\n'
        # is otherwise drawn in the same visual line.
        display=self.text().replace('\r\n','\n').replace('\r','\n').replace('\n','\u2028')
        layout=QTextLayout(display,self.font());options=QTextOption()
        options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(options)
        layout.beginLayout();y=0
        while True:
            line=layout.createLine()
            if not line.isValid():break
            line.setLineWidth(width);line.setPosition(QPointF(0,y));y+=line.height()
        layout.endLayout();self._layout=layout;self._layout_key=key
        return layout

    def line_count(self,width=None):
        if not self.wrap or not self.text():return 1
        layout=self._text_layout(max(1,(self.width() if width is None else width)-37))
        return max(1,layout.lineCount())

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.wrap:
            if hasattr(self,'scrollbar'):self._sync_scrollbar()
            self.textChanged.emit()

    def changeEvent(self,event):
        super().changeEvent(event)
        if getattr(self,'wrap',False) and event.type() in (QEvent.Type.FontChange,QEvent.Type.StyleChange):
            self._layout_key=None
            if hasattr(self,'scrollbar'):
                self._sync_scrollbar();self.textChanged.emit()

    def _sync_scrollbar(self):
        if not self.scrollbar:return
        line_height=max(1,self.fontMetrics().height());visible=max(1,(self.height()-6)//line_height)
        layout=self._text_layout(max(1,self.width()-37));overflow=layout.lineCount()>visible
        if overflow:layout=self._text_layout(max(1,self.width()-47))
        self.scrollbar.setGeometry(max(0,self.width()-10),3,8,max(0,self.height()-6))
        self.scrollbar.setPageStep(visible);self.scrollbar.setRange(0,max(0,layout.lineCount()-visible))
        if self.scrollbar.isHidden()==overflow:self.scrollbar.setVisible(overflow)

    def enterEvent(self,event):
        super().enterEvent(event)
        if self.wrap:self.hoverChanged.emit(True)

    def leaveEvent(self,event):
        super().leaveEvent(event)
        if self.wrap:self.hoverChanged.emit(False)

    def wheelEvent(self,event):
        if self.scrollbar and self.scrollbar.isVisible():
            self.scrollbar.setValue(self.scrollbar.value()-(1 if event.angleDelta().y()>0 else -1));event.accept();return
        super().wheelEvent(event)

    def paintEvent(self,event):
        if not self.text() or self.width()<32:return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setFont(self.font())
        painter.setPen(QPen(QColor('#deeaed'),1));painter.setBrush(QColor('#edf6f5' if self.notice else '#f0f5f7'))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,1,-.5,-1),6,6)
        is_file=any(suffix in self.text().lower() for suffix in ('.tif','.vrt','.geojson','.shp','.json'))
        symbol(painter,QRectF(8,(self.height()-13)/2,13,13),'file' if is_file else 'info','#43838a')
        if self.wrap:
            line_height=max(1,self.fontMetrics().height());overflow=not self.scrollbar.isHidden()
            layout=self._text_layout(max(1,self.width()-47 if overflow else self.width()-37))
            painter.setPen(QColor('#386570' if self.notice else '#526e7a'))
            painter.setClipRect(QRectF(29,3,max(0,self.width()-37-(10 if overflow else 0)),max(0,self.height()-6)))
            top=max(3,(self.height()-line_height)/2) if layout.lineCount()==1 else 3
            offset=layout.lineAt(self.scrollbar.value()).y() if layout.lineCount() else 0
            layout.draw(painter,QPointF(29,top-offset));return
        text=self.text();left=29;first,separator,rest=text.partition(' · ');metrics=painter.fontMetrics()
        # A compact phase capsule precedes the filename, which gets all remaining
        # space. Narrow windows fall back to a single elided line.
        if separator and len(first)<=16 and self.width()>220:
            width=min(metrics.horizontalAdvance(first)+14,int(self.width()*.4))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor('#deedef'))
            painter.drawRoundedRect(QRectF(left,4,width,self.height()-8),4,4)
            painter.setPen(QColor('#36747d'))
            painter.drawText(QRectF(left+7,0,width-14,self.height()),Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(first,Qt.TextElideMode.ElideRight,max(0,width-14)))
            left+=width+9;text=rest
        painter.setPen(QColor('#386570' if self.notice else '#526e7a'))
        painter.drawText(QRectF(left,0,max(0,self.width()-left-8),self.height()),Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(text,Qt.TextElideMode.ElideRight,max(0,self.width()-left-8)))
