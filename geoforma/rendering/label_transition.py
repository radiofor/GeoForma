"""Short, interruptible contour handoff independent of raster transitions."""
from PySide6.QtCore import QObject,QEvent,QVariantAnimation,QEasingCurve,Qt
from PySide6.QtWidgets import QGraphicsPathItem


class LabelTransition(QObject):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.ghosts=[];self.new_items=[]
        self.animation=QVariantAnimation(self);self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance);self.animation.finished.connect(self.cancel)
        view.installEventFilter(self);view.viewport().installEventFilter(self)

    def capture(self):
        records=[]
        for key,item in self.view.overlay_records.items():
            if item.isVisible():records.append((key,item.geometry_value,item.path(),item.pen(),item.zValue(),item.opacity()))
        for key,item,opacity in self.ghosts:
            if item.isVisible() and item.opacity()>0:
                records.append((key,None,item.path(),item.pen(),item.zValue(),item.opacity()))
        return records

    def reveal(self,records):
        self.cancel()
        current=self.view.overlay_records;kept={}
        for key,geometry,path,pen,z,opacity in records:
            item=current.get(key)
            if geometry is not None and item is not None and item.geometry_value is geometry:continue
            kept.setdefault(key,[]).append((path,pen,z,opacity))
        for key,entries in kept.items():
            # Bound retained paths during rapid repeated switches.
            for path,pen,z,opacity in sorted(entries,key=lambda value:value[3],reverse=True)[:3]:
                ghost=QGraphicsPathItem(path);ghost.setPen(pen);ghost.setZValue(z+.01)
                ghost.setAcceptedMouseButtons(Qt.MouseButton.NoButton);ghost.setOpacity(opacity)
                self.view.scene().addItem(ghost);self.ghosts.append((key,ghost,opacity))
            if (item:=current.get(key)) is not None:
                item.setOpacity(0.0);self.new_items.append(item)
        if self.ghosts:
            self.animation.setStartValue(1.0);self.animation.setEndValue(0.0);self.animation.start()

    def advance(self,value):
        for _,item,opacity in self.ghosts:item.setOpacity(opacity*float(value))
        for item in self.new_items:item.setOpacity(1.0-float(value))

    def cancel(self):
        self.animation.stop()
        for _,item,_ in self.ghosts:self.view.scene().removeItem(item)
        self.ghosts.clear()
        for item in self.new_items:item.setOpacity(1.0)
        self.new_items.clear()

    def eventFilter(self,obj,event):
        if self.ghosts and event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonDblClick,
                QEvent.Type.Wheel,QEvent.Type.KeyPress,QEvent.Type.Hide,QEvent.Type.Resize):self.cancel()
        return False
