"""Context-aware draft and saved-label history routing, independent of widgets."""
import copy
from ..ui.text import ui_text


class HistoryWorkflow:
    def flush_label_history(self):
        # Cancelling/confirming a draft must not discard unrelated saved edits.
        for source,target in ((self.prompt_undo,self.label_undo),(self.prompt_redo,self.label_redo)):
            for entry in source:
                if '_label_entries' in entry:
                    entries=entry.pop('_label_entries')
                    if entries:target.append(entries)

    def record_label_operation(self,entries):
        from ..tool_state import has_unsaved_annotation
        if has_unsaved_annotation(self.draft) or self.prompt_context():
            self.prompt_undo.append({**self.geometry_snapshot(),**({'_label_entries':copy.deepcopy(entries)} if entries else {})})
            self.prompt_redo=[]
        else:self.label_undo.append(entries)
        self.label_redo=[]

    def undo_label(self):
        if self.prompt_undo and '_label_entries' in self.prompt_undo[-1]:
            if self.foreground_task_active():return
            self.interrupt_reshape()
            self.restore_geometry_history(self.prompt_undo,self.prompt_redo);return
        if not self.label_undo or self.foreground_task_active():return
        if not self.prepare_label_history(self.label_undo[-1]):return
        self.interrupt_reshape()
        self.label_redo.append(self.restore_label_entries(self.label_undo.pop()))
        self.retain_restored_selection();self.refresh_labels();self.mark_dirty()

    def retain_restored_selection(self):
        # Keep an existing selected label selected after undoing a category or
        # geometry edit; remove IDs that no longer belong to this image.
        live={label['id'] for label in self.current_labels()}
        self.selected_ids.intersection_update(live)
        self.selected_id=next(iter(self.selected_ids)) if len(self.selected_ids)==1 else None

    def restore_label_entries(self,entries):
        from ..label_history import restore_entries
        self.project['labels'],reverse=restore_entries(self.project['labels'],entries)
        return reverse

    def redo_label(self):
        if not self.label_redo or self.foreground_task_active():return
        if not self.prepare_label_history(self.label_redo[-1]):return
        self.interrupt_reshape()
        self.label_undo.append(self.restore_label_entries(self.label_redo.pop()));self.retain_restored_selection();self.refresh_labels();self.mark_dirty()

    def prepare_label_history(self,entries):
        if self.draft.get('base_id') in {e[0] for e in entries}:
            if self.draft_modified():self.statusBar().showMessage(ui_text('labels.edit_selected.004'),3000);return False
            self.clear_draft()
        return True

    def undo_context(self):
        if self.reshape_session is not None and self.reshape_session.get('stroke'):self.undo_reshape_point();return
        if self.draft.get('manual_vertices'):self.undo_manual_vertex();return
        if self.prompt_context():
            if self.foreground_task_active():return
            self.interrupt_reshape();self.undo_prompt()
        else:
            if self.draft:self.clear_draft()
            self.undo_label()

    def redo_context(self):
        if self.reshape_session is not None and self.reshape_session.get('redo_stroke'):self.redo_reshape_point();return
        if self.prompt_context():
            if self.foreground_task_active():return
            self.interrupt_reshape();self.redo_prompt()
        else:
            if self.draft:self.clear_draft()
            self.redo_label()

