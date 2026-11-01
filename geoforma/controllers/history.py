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

    def undo_all_labels(self):
        if not self.label_undo or self.foreground_task_active() or self.reshape_session is not None:return
        # Check the entire history before changing anything: a modified target
        # can occur in an older operation, not just the newest one.
        entries=[entry for operation in self.label_undo for entry in operation]
        if not self.prepare_label_history(entries):return
        if len(self.project['labels'])*len(self.label_undo)>100000:
            from ..label_history import replay_all
            labels=tuple(self.project['labels']);undo=tuple(tuple(operation) for operation in self.label_undo);redo=tuple(self.label_redo)
            images=[{'id':image['id'],'dismissed_candidates':tuple(image.get('dismissed_candidates',()))} for image in self.project['images']]
            context=self.annotation_context()
            def done(result):
                if context!=self.annotation_context():return
                self.project['labels']=result['labels'];self.label_undo=[];self.label_redo=result['redo']
                for image in self.project['images']:
                    if image['id'] in result['dismissed']:image['dismissed_candidates']=result['dismissed'][image['id']]
                self.selected_id=None;self.selected_ids.clear();self.pending_review=None
                self.refresh_labels();self.mark_dirty();self.autosave()
            self.run('全部撤销标签',lambda task:replay_all(labels,undo,redo,images,task),done,kind='history')
            return
        while self.label_undo:
            self.label_redo.append(self.restore_label_entries(self.label_undo.pop()))
        self.selected_id=None;self.selected_ids.clear();self.pending_review=None
        self.refresh_labels();self.mark_dirty();self.autosave()

    def restore_label_entries(self,entries):
        from ..label_history import restore_entries
        self.project['labels'],reverse=restore_entries(self.project['labels'],entries)
        ids={entry[0] for entry in entries}
        restored={identifier for identifier,old,_ in entries if old};removed=ids-restored
        for image in self.project['images']:
            dismissed=set(image.get('dismissed_candidates',[]));dismissed-=restored
            dismissed|={identifier for identifier,current,_ in reverse if identifier in removed and current and current['image_id']==image['id']}
            image['dismissed_candidates']=sorted(dismissed)
        if self.image and self.image not in self.project['images']:
            self.image['dismissed_candidates']=sorted(set(self.image.get('dismissed_candidates',[]))-restored|removed)
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

