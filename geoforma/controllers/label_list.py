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

    def candidate_signature(self):
        return (self.image['id'] if self.image else None,
                tuple((l['id'],l['status'],id(l['geometry']),l.get('score'),bool(l.get('edge')),l.get('class_id')) for l in self.current_labels()),
                self.annotation_mode())

    def ensure_candidate_index(self):
        key=self.candidate_signature()
        if self.candidate_key==key:return True
        context=self.annotation_context();cached=self.candidate_indexes.get(context)
        if cached and cached[0]==key:self.candidate_key,self.candidate_index=cached;return True
        from ..operation_state import interaction_locked
        if interaction_locked(self):return False
        labels=self.current_labels()
        if len(labels)<=32 and sum(vertex_count(l['geometry']) for l in labels)<=4096:
            self.candidate_index=LabelIndex(labels);self.candidate_key=key
            self.candidate_indexes[context]=(key,self.candidate_index);return True
        if self.candidate_task is None and not self.closing:
            snapshot=[dict(label) for label in labels];task=Task(lambda t:LabelIndex(snapshot,task=t));self.candidate_task=task
            self.background_activity.set('labels','准备标签',f'{len(labels)} 个目标',task)
            def ready(index):
                if context==self.annotation_context() and key==self.candidate_signature():
                    self.candidate_index=index;self.candidate_key=key;self.candidate_indexes[context]=(key,index)
            def failed(message):
                if task.cancel_event.is_set():return
                self.log_message('准备标签失败：'+message)
                if context==self.annotation_context() and key==self.candidate_signature():
                    if not self.candidate_key or self.candidate_key[0]!=key[0]:self.candidate_index=LabelIndex([])
                    self.candidate_key=key
                    self.statusBar().showMessage('轮廓显示失败，标签记录保留。详细信息见任务记录。',7000)
            def finished():
                if self.candidate_task is task:self.candidate_task=None
                self.background_activity.set('labels','')
                if self.closing:QTimer.singleShot(0,self.close)
                else:self.refresh_labels()
            task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished)
            self.candidate_pool.start(task)
        return False

    def current_batch_labels(self):return self.current_labels()

    def presentation_labels(self):
        if self.candidate_index is None or not self.candidate_key:return []
        signature=self.candidate_signature()
        if (self.candidate_key[0],self.candidate_key[2])!=(signature[0],signature[2]):return []
        saved,candidates=self.candidate_index.visible(self.draft);live={l['id'] for l in self.current_labels()}
        selected=self.label_filter.currentIndex()
        return [l for l in ([] if selected==2 else saved)+([] if selected==1 else candidates) if l['id'] in live]

    def refresh_labels(self):
        labels=self.current_labels();ready=self.ensure_candidate_index();visible=self.presentation_labels()
        saved=[l for l in labels if l['status']=='confirmed'] if self.label_filter.currentIndex()!=2 else []
        candidates=[l for l in visible if l['status']=='candidate'];base=self.draft.get('base_id')
        table=saved+candidates
        if base and base not in {l['id'] for l in table}:
            original=next((l for l in labels if l['id']==base),None)
            if original and self.label_filter.currentIndex() in (0,1 if original['status']=='confirmed' else 2):
                if original['status']=='candidate':
                    candidates.append(original)
                    if self.candidate_index:
                        order={label['id']:i for i,label in enumerate(self.candidate_index.candidates)}
                        candidates.sort(key=lambda label:order.get(label['id'],len(order)))
                    table=saved+candidates
                else:table.insert(0,original)
        drafts=self.draft_labels();draft_ids={d['id'] for d in drafts}
        # Replace existing edited rows in place, and append new components.
        replacements={d['id']:d for d in drafts}
        table=[replacements.get(l['id'],l) for l in table]
        listed={l['id'] for l in table}
        table.extend(d for d in drafts if d['id'] not in listed)
        if ready:
            self.selected_ids.intersection_update({l['id'] for l in table}|({base} if base else set()))
        self.selected_id=next(iter(self.selected_ids)) if len(self.selected_ids)==1 else None
        self.label_count.set_counts(sum(l['status']=='confirmed' for l in labels),
                                    len(self.candidate_index.candidates) if ready else sum(l['status']=='candidate' for l in labels),ready=ready)
        names={c['id']:c['name'] for c in self.project['classes']};rows=[]
        editing=self.reshape_session['label']['id'] if self.reshape_session else base
        editing_ids={editing}|{d.get('base_id') for d in self.draft.get('reshape_batch',[])}
        from ..ui.label_table import LabelRow
        for position,label in enumerate(table):
            title=names.get(label.get('class_id'),'未分类') if label['status'] in ('confirmed','draft') else f'候选 {position+1}'
            status=ui_text('status.unsaved' if label['id'] in draft_ids else 'status.editing' if label['id'] in editing_ids else 'status.confirmed' if label['status']=='confirmed' else 'status.review')
            rows.append(LabelRow(label['id'],title,status,bool(label.get('edge')),label['id'] in self.selected_ids,label.get('class_id')))
        self.label_presenter.set_categories(self.project['classes'],self.change_label_class)
        self.label_presenter.sync(rows);self.redraw();self.update_controls()

    def review_target(self,step=1):
        if self.foreground_task_active() or self.reshape_session is not None:return
        ids=[row.identifier for row in self.label_presenter.rows]
        if not ids:return
        current=self.selected_id
        position=(ids.index(current)+step)%len(ids) if current in ids else (0 if step>0 else len(ids)-1)
        self.select_label(ids[position]);self.zoom_selected()
