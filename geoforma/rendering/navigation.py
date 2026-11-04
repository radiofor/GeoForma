"""Screen-space navigation and scrollbar policy; no model or annotation mutation."""
from PySide6.QtCore import Qt,QTimer,QPointF
from PySide6.QtWidgets import QGraphicsView


class ViewNavigation:
    def capture_navigation(self):
        center=self.viewportTransform().inverted()[0].map(QPointF(self.viewport().width()/2,self.viewport().height()/2))
        return {'scale':self.transform().m11(),'center':[center.x(),center.y()]}

    def restore_navigation(self,state):
        self.resetTransform();self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        scale=state['scale'];self.scale(scale,scale)
        pad=2*max(self.raster_rect.width(),self.raster_rect.height(),self.viewport().width()/scale,self.viewport().height()/scale)
        self.setSceneRect(self.raster_rect.adjusted(-pad,-pad,pad,pad));self.centerOn(*state['center'])
        self.update_scrollbar_visibility();self.centerOn(*state['center']);self.viewportChanged.emit()

    def initialize_navigation(self):
        self.scrollbar_timer=QTimer(self);self.scrollbar_timer.setSingleShot(True);self.scrollbar_timer.timeout.connect(self.update_scrollbar_visibility)
        self.viewportChanged.connect(self.schedule_scrollbars)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def scrollContentsBy(self,dx,dy):
        super().scrollContentsBy(dx,dy)
        # Repaint the screen-fixed backdrop after Qt moves old viewport pixels.
        self.viewport().update()
        self.schedule_scrollbars()

    def schedule_scrollbars(self):
        if hasattr(self,'scrollbar_timer') and not self.scrollbar_timer.isActive():self.scrollbar_timer.start(0)

    def update_scrollbar_visibility(self):
        # Navigation margins support cursor-centred zoom, but are not image data.
        bounds=self.viewportTransform().mapRect(self.raster_rect)
        viewport=self.viewport().rect()
        has_image=not self.raster_rect.isEmpty()
        horizontal=has_image and (bounds.left() < -2 or bounds.right() > viewport.width()+2)
        vertical=has_image and (bounds.top() < -2 or bounds.bottom() > viewport.height()+2)
        for needed,policy,setter in ((horizontal,self.horizontalScrollBarPolicy(),self.setHorizontalScrollBarPolicy),
                                      (vertical,self.verticalScrollBarPolicy(),self.setVerticalScrollBarPolicy)):
            desired=Qt.ScrollBarPolicy.ScrollBarAlwaysOn if needed else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            if policy!=desired:setter(desired)

    def fit_image(self):
        if not self.raster_rect.isEmpty():
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setSceneRect(self.raster_rect);self.fitInView(self.raster_rect,Qt.AspectRatioMode.KeepAspectRatio);self.viewportChanged.emit()

    def wheelEvent(self,event):
        if self.raster_rect.isEmpty():event.accept();return
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if not delta:event.ignore();return
        self.zoom_at(event.position().toPoint(),1.25 if delta>0 else .8);event.accept()

    def zoom_at(self,position,factor):
        if self.raster_rect.isEmpty():return
        scale=self.transform().m11()*factor
        if not 1e-6<scale<64:return
        before=self.mapToScene(position);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(factor,factor)
        # Keep scrollable margins even when the image is smaller than the view.
        pad=2*max(self.raster_rect.width(),self.raster_rect.height(),self.viewport().width()/scale,self.viewport().height()/scale)
        self.setSceneRect(self.raster_rect.adjusted(-pad,-pad,pad,pad))
        after=self.mapToScene(position);self.translate(after.x()-before.x(),after.y()-before.y());self.viewportChanged.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'empty'):self.empty.move((self.viewport().width()-self.empty.width())//2,(self.viewport().height()-self.empty.height())//2)
        if hasattr(self,'loading'):self.loading.move((self.viewport().width()-self.loading.width())//2,(self.viewport().height()-self.loading.height())//2)
        self.viewportChanged.emit()
