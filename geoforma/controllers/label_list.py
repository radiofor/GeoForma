"""Incremental label table and asynchronous geometry presentation."""
from PySide6.QtCore import QTimer
from ..label_index import LabelIndex,vertex_count
from ..tasks import Task
from ..ui.text import ui_text


class LabelListWorkflow:
    def draft_labels(self):
        """Stable identities shared by unsaved rows, canvas hit tests and saving."""
        from ..domain import uid
        from ..label_parts import split_label
        records=[];cache=getattr(self,'_draft_parts_cache',{})
        live_cache={}
        for draft in self.draft.get('reshape_batch') or [self.draft]:
            geometry=draft.get('geometry')
            if not geometry:continue
            if draft.get('class_id') is None:draft['class_id']=self.classes.currentData()
            ids=draft.setdefault('display_ids',[])
            if not ids:ids.append(draft.get('base_id') or uid())
            if draft.get('base_id'):ids[0]=draft['base_id']
            cache_key=(id(geometry),ids[0]);cached=cache.get(cache_key)
            if cached and cached[0] is geometry:parts=cached[1]
            else:parts=split_label({'id':ids[0],'geometry':geometry},ids)
            for i,part in enumerate(parts):
                if i>=len(ids):ids.append(part['id'])
            live_cache[cache_key]=(geometry,parts)
            category=draft.get('class_id') if self.draft.get('reshape_batch') else self.classes.currentData()
            for part in parts:
                records.append(dict(part,image_id=self.image['id'] if self.image else None,class_id=draft.get('part_classes',{}).get(part['id'],category),
                    status='draft',editing_state=draft.get('editing_state','model'),box=draft.get('box'),
                    _draft_root=ids[0],model={'single_polygon':self.single_polygon.isChecked()}))
        self._draft_parts_cache=live_cache
        return records

    def label_index_signature(self,labels=None):
        if labels is None:labels=self.current_labels()
        return (self.image['id'] if self.image else None,
                tuple((l['id'],l['status'],id(l['geometry']),l.get('score'),bool(l.get('edge')),l.get('class_id')) for l in labels),
                self.annotation_mode())

    def ensure_label_index(self,labels=None):
        if labels is None:labels=self.current_labels()
        key=self.label_index_signature(labels)
        if self.label_index_key==key:return True
        context=self.annotation_context();cached=self.label_indexes.get(context,key)
        if cached is not None:self.label_index_key,self.label_index=key,cached;return True
        from ..operation_state import interaction_locked
        if interaction_locked(self):return False
        if len(labels)<=32 and sum(vertex_count(l['geometry']) for l in labels)<=4096:
            self.label_index=LabelIndex(labels);self.label_index_key=key
            self.label_indexes.put(context,key,self.label_index);return True
        if self.label_index_task is None and not self.closing:
            snapshot=[dict(label) for label in labels];task=Task(lambda t:LabelIndex(snapshot,task=t));self.label_index_task=task
            self.background_activity.set('labels','准备标签',f'{len(labels)} 个目标',task)
            def ready(index):
                if context==self.annotation_context() and key==self.label_index_signature():
                    self.label_index=index;self.label_index_key=key;self.label_indexes.put(context,key,index)
            def failed(message):
                if task.cancel_event.is_set():return
                self.log_message('准备标签失败：'+message)
                if context==self.annotation_context() and key==self.label_index_signature():
                    if not self.label_index_key or self.label_index_key[0]!=key[0]:self.label_index=LabelIndex([])
                    self.label_index_key=key
                    self.statusBar().showMessage('轮廓显示失败，标签记录保留。详细信息见任务记录。',7000)
            def finished():
                if self.label_index_task is task:self.label_index_task=None
                self.background_activity.set('labels','')
                if self.closing:QTimer.singleShot(0,self.close)
                else:self.refresh_labels()
            task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished)
            self.label_index_pool.start(task)
        return False

    def presentation_labels(self,labels=None):
        if self.label_index is None or not self.label_index_key:return []
        if (self.label_index_key[0],self.label_index_key[2])!=(self.image['id'] if self.image else None,self.annotation_mode()):return []
        if labels is None:labels=self.current_labels()
        saved=self.label_index.visible(self.draft);live={l['id'] for l in labels}
        return [l for l in saved if l['id'] in live]

    def refresh_labels(self):
        labels=self.current_labels();ready=self.ensure_label_index(labels)
        base=self.draft.get('base_id');table=labels
        drafts=self.draft_labels();draft_ids={d['id'] for d in drafts}
        # Replace existing edited rows in place, and append new components.
        replacements={d['id']:d for d in drafts}
        table=[replacements.get(l['id'],l) for l in table]
        listed={l['id'] for l in table}
        table.extend(d for d in drafts if d['id'] not in listed)
        if ready:
            self.selected_ids.intersection_update({l['id'] for l in table}|({base} if base else set()))
        self.selected_id=next(iter(self.selected_ids)) if len(self.selected_ids)==1 else None
        names={c['id']:c['name'] for c in self.project['classes']};rows=[]
        editing=self.reshape_session['label']['id'] if self.reshape_session else base
        editing_ids={editing}|{d.get('base_id') for d in self.draft.get('reshape_batch',[])}
        from ..ui.label_table import LabelRow
        for label in table:
            title=names.get(label.get('class_id'),'未分类')
            status=ui_text('status.unsaved' if label['id'] in draft_ids else 'status.editing' if label['id'] in editing_ids else 'status.confirmed')
            rows.append(LabelRow(label['id'],title,status,bool(label.get('edge')),label['id'] in self.selected_ids,label.get('class_id')))
        self.label_presenter.sync(rows);self.redraw();self.update_controls()
