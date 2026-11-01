"""Small vector badges and inset details; updates never change status geometry."""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
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
    def __init__(self,text='',parent=None,notice=False):
        super().__init__(text,parent);self.notice=notice

    def paintEvent(self,event):
        if not self.text() or self.width()<32:return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setFont(self.font())
        painter.setPen(QPen(QColor('#deeaed'),1));painter.setBrush(QColor('#edf6f5' if self.notice else '#f0f5f7'))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,1,-.5,-1),6,6)
        is_file=any(suffix in self.text().lower() for suffix in ('.tif','.vrt','.geojson','.shp','.json'))
        symbol(painter,QRectF(8,(self.height()-13)/2,13,13),'file' if is_file else 'info','#43838a')
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
