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
        if self.draft or self.prompt_context():
            self.prompt_undo.append({**self.geometry_snapshot(),**({'_label_entries':copy.deepcopy(entries)} if entries else {})})
            self.prompt_redo=[]
        else:self.label_undo.append(entries)
        self.label_redo=[]

    def undo_label(self):
        if self.prompt_undo and '_label_entries' in self.prompt_undo[-1]:
            self.restore_geometry_history(self.prompt_undo,self.prompt_redo);return
        if not self.label_undo or self.foreground_task_active() or self.reshape_session is not None:return
        if not self.prepare_label_history(self.label_undo[-1]):return
        self.label_redo.append(self.restore_label_entries(self.label_undo.pop()))
        self.selected_id=None;self.selected_ids.clear();self.refresh_labels();self.mark_dirty()

    def restore_label_entries(self,entries):
        from ..label_history import restore_entries
        self.project['labels'],reverse=restore_entries(self.project['labels'],entries)
        return reverse

    def redo_label(self):
        if not self.label_redo or self.foreground_task_active() or self.reshape_session is not None:return
        if not self.prepare_label_history(self.label_redo[-1]):return
        self.label_undo.append(self.restore_label_entries(self.label_redo.pop()));self.selected_id=None;self.selected_ids.clear();self.refresh_labels();self.mark_dirty()

    def prepare_label_history(self,entries):
        if self.draft.get('base_id') in {e[0] for e in entries}:
            if self.draft_modified():self.statusBar().showMessage(ui_text('labels.edit_selected.004'),3000);return False
            self.clear_draft()
        return True

    def undo_context(self):
        if self.reshape_session is not None:self.undo_reshape_point();return
        if self.draft.get('manual_vertices'):self.undo_manual_vertex();return
        if self.prompt_context():self.undo_prompt()
        else:
            if self.draft:self.clear_draft()
            self.undo_label()

    def redo_context(self):
        if self.reshape_session is not None:self.redo_reshape_point();return
        if self.prompt_context():self.redo_prompt()
        else:
            if self.draft:self.clear_draft()
            self.redo_label()

