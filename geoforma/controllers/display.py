"""DisplayWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from PySide6.QtCore import QTimer


class DisplayWorkflow:
    def request_render(self,overview=False):
        if self.closing:return
        if not self.image or not self.image.get('display_recipe'):return
        if self.reference_transition_pending and not overview:return
        im=self.display_image();window=[0,0,im['width'],im['height']] if overview else self.view.visible_window();size=1400 if overview else max(800,min(2200,max(self.view.viewport().width(),self.view.viewport().height())*2))
        self.raster_renderer.request(im,self.render_generation,window,size,overview)

    def apply_raster(self,value,window,overview):
        if self.closing:return
        switching=overview and self.reference_transition_pending
        viewport=self.view.viewport()
        updates=viewport.updatesEnabled()
        if switching and updates:viewport.setUpdatesEnabled(False)
        try:
            self.view.show_raster(*value,window,overview)
            if overview:
                if self.view.layers.raster_epoch!=self.render_generation:self.view.layers.clear_detail()
                self.view.layers.raster_epoch=self.render_generation;self.render_timer.stop()
                generation=self.render_generation
                QTimer.singleShot(0,self,lambda:self.request_render() if not self.closing and self.render_generation==generation and not self.render_timer.isActive() else None)
            if switching:self.reference_transition_pending=False;self.visible_reference=self.display_reference
        finally:
            if switching and updates:viewport.setUpdatesEnabled(True);viewport.update()
        # Raster arrival changes only pixels. Labels are refreshed by annotation
        # and index events, so panning never walks or restyles every polygon.

    def render_finished(self):
        self.render_task=None
        if self.closing and not self.task:QTimer.singleShot(0,self.close)

    def zoom_native(self):
        if not self.image or self.view.raster_rect.isEmpty():return
        self.view.resetTransform();self.view.viewportChanged.emit()

    def invalidate_preview(self):
        self.view.clear_preview()
