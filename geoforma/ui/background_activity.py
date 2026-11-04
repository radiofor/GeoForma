"""Summarize independent workers without sharing their progress or cancellation."""
from PySide6.QtCore import QObject,QTimer,Qt


class BackgroundActivity(QObject):
    ORDER=('raster','labels','smoothing','autosave')

    def __init__(self,window,button,menu,delay=200):
        super().__init__(window);self.window=window;self.button=button;self.menu=menu
        self.delay=delay;self.entries={};self.visible={};self.owns_text=False;self.signature=()

    def set(self,key,title,detail='',token=None):
        if not title:
            self.entries.pop(key,None);self.visible.pop(key,None);self.refresh();return
        record=(title,detail,token);marker=object();self.entries[key]=(marker,record)
        if key in self.visible:
            self.visible[key]=record;self.refresh();return
        def reveal():
            if self.entries.get(key,(None,))[0] is marker:
                self.visible[key]=record;self.refresh()
        QTimer.singleShot(self.delay,self,reveal)

    def raster_changed(self,task):
        if task is None:self.set('raster','');return
        request=self.window.raster_renderer.active_request
        image=request.image;reference=image.get('_reference')
        from ..reference_images import MAIN_IMAGE_LABEL
        title=('显示 '+reference['group']+' 参考') if reference else '显示'+MAIN_IMAGE_LABEL
        from pathlib import Path
        self.set('raster',title,Path(image['path']).name,task)

    def smoothing_changed(self,task):
        self.set('smoothing','平滑标签' if task else '',token=task)

    def refresh(self):
        w=self.window
        records=[self.visible[key] for key in self.ORDER if key in self.visible]
        signature=tuple((title,detail) for title,detail,_ in records)
        if signature!=self.signature:
            self.signature=signature;self.menu.clear()
            for title,detail in signature:
                action=self.menu.addAction(title+(' · '+detail if detail else ''));action.setEnabled(False)
            summary=f'后台 {len(records)} 项' if records else ''
            self.button.setText(self.button.fontMetrics().elidedText(summary,Qt.TextElideMode.ElideRight,self.button.width()-16))
            self.button.setToolTip('\n'.join(title+('：'+detail if detail else '') for title,detail in signature))
            self.button.setEnabled(bool(records))
            self.button.setVisible(bool(records))
        primary=w.task is not None or w.progress_presentation.loading_active
        w.statusBar().set_task_active(primary)
        # Background work owns only its own button and menu. It must not replace
        # the foreground task's last result or borrow its progress indicator.
