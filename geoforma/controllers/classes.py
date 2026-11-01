"""ClassWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations


class ClassWorkflow:
    def change_label_class(self,identifier,category):
        from ..operation_state import interaction_locked
        if interaction_locked(self) or self.foreground_task_active() or self.reshape_session is not None:return
        if category not in {c['id'] for c in self.project['classes']}:return
        self.draft_labels()
        for draft in self.draft.get('reshape_batch') or [self.draft]:
            if identifier in draft.get('display_ids',[]):
                self.prompt_undo.append(self.geometry_snapshot());self.prompt_redo=[]
                draft.setdefault('part_classes',{})[identifier]=category
                self.refresh_labels();self.mark_dirty();self.autosave();return
        import copy
        index=next((i for i,l in enumerate(self.project['labels']) if l['id']==identifier),None)
        if index is None or self.project['labels'][index].get('class_id')==category:return
        old=self.project['labels'][index]
        self.record_label_operation([(identifier,copy.deepcopy(old),index)])
        self.project['labels']=[dict(label,class_id=category) if label['id']==identifier else label for label in self.project['labels']]
        self.refresh_labels();self.mark_dirty();self.autosave()

    def refresh_classes(self):
        from ..class_colors import class_color
        from ..ui.color_controls import color_icon
        from PySide6.QtCore import QSize
        current=self.classes.currentData();blocked=self.classes.blockSignals(True);self.classes.clear()
        self.classes.setIconSize(QSize(20,14))
        for c in self.project['classes']:self.classes.addItem(color_icon(class_color(c)),c['name'],c['id'])
        if current:self.classes.setCurrentIndex(max(0,self.classes.findData(current)))
        else:self.classes.setCurrentIndex(0 if self.classes.count() else -1)
        self.classes.blockSignals(blocked)

    def add_class(self):
        self.manage_classes()

    def class_changed(self,*args):
        if self.draft:
            self.prompt_undo.append(self.geometry_snapshot());self.prompt_redo=[]
            self.draft['class_id']=self.classes.currentData();self.mark_dirty()
        self.refresh_labels()

    def manage_classes(self):
        from ..operation_state import can_start_operation,background_prefetch
        if not can_start_operation(self) and not background_prefetch(self):return
        from ..classes import next_class_id,referenced_class_ids
        from ..dialogs import ClassesDialog
        histories=[self.label_undo,self.label_redo]
        for undo,redo in self.mode_histories.values():histories.extend((undo,redo))
        used=referenced_class_ids(self.project['labels'],*histories)
        from ..editing_state import referenced_draft_classes
        used|=referenced_draft_classes(self.draft,self.prompt_undo,self.prompt_redo,*self.project['images'],*self.image_sessions.values())
        from ..ui.modal import dialog_result
        accepted,value=dialog_result(ClassesDialog(self.project['classes'],next_class_id(self.project),used,self.classes.currentData(),self),lambda dialog:dialog.value())
        if not accepted:return
        classes,next_id,selected=value
        self.project['classes']=[dict(c) for c in classes];self.project['next_class_id']=next_id
        self.refresh_classes();self.classes.setCurrentIndex(self.classes.findData(selected));self.refresh_labels();self.update_controls();self.mark_dirty()

