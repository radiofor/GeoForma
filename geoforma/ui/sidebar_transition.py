"""Reveal a resized raster list using cached slices, without scaling text."""
from PySide6.QtCore import QPoint,QRectF,Qt
from PySide6.QtGui import QColor


def sidebar_layout(window):
    view=getattr(window,'images',None);scroll=getattr(window,'image_scroll',None)
    if view is None or scroll is None:return None
    viewport=scroll.viewport()
    return (QRectF(view.mapTo(window,QPoint()),view.size()),
            QRectF(viewport.mapTo(window,QPoint()),viewport.size()))


class SidebarTransition:
    def __init__(self,before,after):self.before,self.after=before,after

    @classmethod
    def create(cls,before,after):
        if before is None or after is None:return None
        old,viewport=before;new,current=after
        if viewport!=current or old.x()!=new.x() or old.y()!=new.y() or old.width()!=new.width():return None
        if old.height()==new.height() or not viewport.contains(old) or not viewport.contains(new):return None
        return cls(before,after)

    def paint(self,painter,frame,old_snapshot,new_snapshot,blend):
        old,viewport=self.before;new,_=self.after
        height=new.height()+(old.height()-new.height())*blend
        current=QRectF(new.x(),new.y(),new.width(),height)
        painter.save();painter.setClipRect(viewport);painter.setOpacity(1.)
        painter.fillRect(viewport,QColor('#f6f9fa'))

        def slice(snapshot,destination,source_y,source_height,opacity):
            height=min(destination.height(),source_height)
            if height<=0 or opacity<=0:return
            painter.save();painter.setClipRect(QRectF(destination.x(),destination.y(),destination.width(),height),Qt.ClipOperation.IntersectClip)
            painter.setOpacity(opacity);painter.translate(0,destination.y()-source_y)
            painter.drawPixmap(frame,snapshot);painter.restore()

        def pair(destination,old_y,old_height,new_y,new_height):
            slice(new_snapshot,destination,new_y,new_height,1.)
            slice(old_snapshot,destination,old_y,old_height,blend)

        # Everything above the list stays in place. Beneath it, both cached
        # tails move together, rather than fading between different positions.
        top=QRectF(viewport.x(),viewport.y(),viewport.width(),current.y()-viewport.y())
        pair(top,viewport.y(),top.height(),viewport.y(),top.height())
        # The card's vertical walls sit outside the list. Preserve those too,
        # including the white margins and border, throughout the reveal.
        source,snapshot=(new,new_snapshot) if new.height()>=old.height() else (old,old_snapshot)
        for x,width in ((viewport.x(),current.x()-viewport.x()),
                        (current.x()+current.width(),viewport.x()+viewport.width()-current.x()-current.width())):
            slice(snapshot,QRectF(x,current.y(),width,height),source.y(),source.height(),1.)
        painter.fillRect(current,QColor('white'))
        cap=8.
        pair(QRectF(current.x(),current.y(),current.width(),cap),old.y(),cap,new.y(),cap)
        body=QRectF(current.x(),current.y()+cap,current.width(),height-2*cap)
        pair(body,old.y()+cap,old.height()-2*cap,new.y()+cap,new.height()-2*cap)
        pair(QRectF(current.x(),current.y()+height-cap,current.width(),cap),
             old.y()+old.height()-cap,cap,new.y()+new.height()-cap,cap)
        tail=QRectF(viewport.x(),current.y()+height,viewport.width(),viewport.y()+viewport.height()-current.y()-height)
        pair(tail,old.y()+old.height(),viewport.y()+viewport.height()-old.y()-old.height(),
             new.y()+new.height(),viewport.y()+viewport.height()-new.y()-new.height())
        painter.restore()
