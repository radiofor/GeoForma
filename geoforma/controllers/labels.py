"""LabelWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy
from datetime import datetime
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QMessageBox
from shapely.geometry import shape
from ..domain import uid


class LabelWorkflow:
    def save_label_with_enter(self):
        if self.confirm_button.isEnabled():self.confirm_button.click()

    def redraw(self):
        self.view.set_annotation_context(self.annotation_context())
        labels=self.presentation_labels();base=self.draft.get('base_id')
        batch={d.get('base_id'):d for d in self.draft.get('reshape_batch',[]) if d.get('base_id')}
        from ..editing_state import batch_labels
        labels=batch_labels(labels,self.draft)
        active=not base or any(l['id']==base for l in self.current_batch_labels())
        reshape=self.reshape_session
        preview=reshape.get('preview') if reshape else None
        if preview:labels=[dict(label,geometry=preview['geometry']) if label['id']==reshape['label']['id'] else label for label in labels]
        draft_geometry=self.draft.get('geometry') if active and (not reshape or reshape.get('target') in ('draft','auto')) else None
        if reshape and reshape.get('target')=='draft':
            labels=[label for label in labels if label['id']!=base]
            draft_geometry=preview['geometry'] if preview else reshape['label']['geometry']
        labels,draft_geometry=self.smooth_display(labels,draft_geometry)
        staged=self.draft_labels()
        if staged and draft_geometry:
            from ..label_parts import split_label
            # The first contour retains the dedicated draft scene item; other
            # components have their own retained items and table identities.
            display=split_label({'id':staged[0]['id'],'geometry':draft_geometry},[d['id'] for d in staged])
            draft_geometry=display[0]['geometry']
            labels.extend(dict(staged[i],geometry=part['geometry']) for i,part in enumerate(display) if i)
        if staged:
            groups={}
            for d in staged:groups.setdefault(d['_draft_root'],[]).append(d)
            expanded=[]
            for label in labels:
                group=groups.get(label['id'])
                if group and len(group)>1:
                    from ..label_parts import split_label
                    parts=split_label(label,[d['id'] for d in group])
                    expanded.extend(dict(d,geometry=part['geometry']) for d,part in zip(group,parts))
                else:expanded.append(label)
            labels=expanded
        editing_id=reshape['label']['id'] if reshape else base if active else None
        if batch:editing_id=set(batch)
        if staged:editing_id={d['id'] for d in staged}
        from ..class_colors import color_map
        self.view.overlays(labels,draft_geometry,self.selected_ids,pending=bool(self.draft.get('pending')),draft_id=staged[0]['id'] if staged else base,editing_id=editing_id,class_colors=color_map(self.project['classes']))
        self.view.prompts(self.draft.get('points',[]) if active else [],self.draft.get('box') if active else None,self.selected_points)

    def table_selected(self):
        self.selected_ids={self.labels_table.item(index.row(),0).data(Qt.ItemDataRole.UserRole) for index in self.labels_table.selectionModel().selectedRows()}
        self.selected_id=next(iter(self.selected_ids)) if len(self.selected_ids)==1 else None
        self.refresh_labels()

    def select_label(self,identifier):
        self.selected_id=identifier;self.selected_ids={identifier};self.refresh_labels()

    def select_items(self,kind,values,additive=False,toggle=False):
        from ..operation_state import can_browse,interaction_locked
        if interaction_locked(self) or self.reshape_session is not None or (self.prompt_task_busy() if kind=='points' else not can_browse(self)):return
        current=self.selected_points if kind=='points' else self.selected_ids;values=set(values)
        selection=(current.symmetric_difference(values) if toggle else current|values) if additive else values
        if kind=='points':
            self.selected_points=selection;self.update_draft_info();self.redraw();self.update_controls()
        else:
            self.selected_ids=selection;self.selected_id=next(iter(selection)) if len(selection)==1 else None;self.refresh_labels()

    def delete_selection(self):
        focus=self.focusWidget();table_focus=focus is self.labels_table or focus is not None and self.labels_table.isAncestorOf(focus)
        if self.selected_points and not table_focus:self.delete_points()
        else:self.delete_selected()

    def selected_label(self):
        draft=next((d for d in self.draft_labels() if d['id']==self.selected_id),None)
        if draft:return draft
        return self.label_lookup.for_id(self.project['labels'],self.image['id'],self.selected_id) if self.image else None

    def editable_label(self,label):
        if label and label['status']=='candidate' and self.candidate_index and self.candidate_key==self.candidate_signature():
            resolved=self.candidate_index.by_id.get(label['id'])
            if resolved:return resolved
        return label

    def zoom_selected(self):
        label=self.selected_label()
        if label:
            x0,y0,x1,y1=shape(label['geometry']).bounds;pad=max(40,(max(x1-x0,y1-y0))*.15);self.view.fitInView(QRectF(x0-pad,y0-pad,x1-x0+2*pad,y1-y0+2*pad),Qt.AspectRatioMode.KeepAspectRatio);self.view.viewportChanged.emit()

    def edit_selected(self,checked=False,activate_tool=True,locate=True):
        if self.foreground_task_active():return
        label=self.editable_label(self.selected_label())
        if not label:return
        if label['status']=='draft':
            if locate:self.zoom_selected()
            return
        if self.draft.get('base_id')==label['id']:
            if locate:self.zoom_selected()
            return
        if self.draft_modified():self.statusBar().showMessage(ui_text('labels.edit_selected.004'),3000);return
        if locate:self.zoom_selected()
        self.clear_draft();self.selected_id=None;self.selected_ids.clear()
        self.draft={'base_id':label['id'],'geometry':copy.deepcopy(label['geometry']),'seed_geometry':copy.deepcopy(label['geometry']),'window':copy.deepcopy(label.get('window')),'points':[],'box':None,'edge':label.get('edge',False),'score':label.get('score'),'model_metadata':copy.deepcopy(label.get('model',{})),'editing_state':label.get('editing_state','model')}
        if label.get('source')=='manual_draw':self.draft['source']='manual_draw'
        if label.get('manual_edits'):self.draft['manual_edits']=copy.deepcopy(label['manual_edits'])
        if label.get('class_id'):self.classes.setCurrentIndex(max(0,self.classes.findData(label['class_id'])))
        self.draft['class_id']=self.classes.currentData();self.draft['initial_class_id']=self.classes.currentData()
        self.update_draft_info();self.refresh_labels();self.update_controls();self.mark_dirty()

    def accept_selected(self):
        label=self.selected_label()
        if label and label['status']=='candidate' and not self.foreground_task_active():self.edit_selected();self.confirm()

    def delete_selected(self):
        if self.foreground_task_active() or self.reshape_session is not None:return
        drafts=self.draft_labels();chosen=self.selected_ids or {self.draft.get('base_id')}
        saved_ids={l['id'] for l in self.current_labels()};draft_ids={d['id'] for d in drafts}
        deleted=chosen&(saved_ids|draft_ids)
        if not deleted:return
        entries=[(l['id'],copy.deepcopy(l),i) for i,l in enumerate(self.project['labels']) if l['id'] in deleted]
        self.record_label_operation(entries)
        from ..draft_parts import remove_parts
        self.draft=remove_parts(self.draft,drafts,deleted)
        self.project['labels']=[l for l in self.project['labels'] if l['id'] not in deleted]
        self.image['dismissed_candidates']=sorted(set(self.image.get('dismissed_candidates',[]))|(deleted&saved_ids))
        self.selected_id=None;self.selected_ids.clear();self.selected_points.clear();self.pending_review=None
        self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview()
        self.refresh_labels();self.mark_dirty();self.autosave()

    def confirm(self):
        if self.draft.get('reshape_batch'):
            self.confirm_reshape_batch();return
        if not self.draft and self.selected_label() and self.selected_label()['status']=='candidate':
            self.edit_selected(activate_tool=False,locate=False)
        if self.foreground_task_active() or self.reshape_session is not None or not self.draft.get('geometry') or self.draft.get('pending'):return
        if self.classes.currentData() is None:self.statusBar().showMessage(ui_text('labels.confirm.005'),3000);return
        from ..session_validation import validate_draft
        try:validate_draft(self.draft,self.image['id'],{i['id'] for i in self.project['images']}|{self.image['id']},{l['id']:l for l in self.project['labels']},{c['id'] for c in self.project['classes']})
        except ValueError as error:self.statusBar().showMessage(str(error),5000);return
        identifier=self.draft.get('base_id') or (self.draft.get('display_ids') or [None])[0] or uid();old=next((copy.deepcopy(l) for l in self.project['labels'] if l['id']==identifier),None)
        continue_review=old and old['status']=='candidate' and self.label_filter.currentIndex()!=1
        review_position=list(shape(self.draft['geometry']).bounds)[:2] if continue_review else None
        label={k:copy.deepcopy(self.draft.get(k)) for k in ['geometry','points','box','window','edge','score','feature_key']}
        for key in ('prompt_scope','prompt_group'):
            if key in self.draft:label[key]=self.draft[key]
        if self.draft.get('editing_state')=='manual':
            label['editing_state']='manual';label['manual_edits']=copy.deepcopy(self.draft.get('manual_edits',(old or {}).get('manual_edits',[])))
            if old and old.get('editing_state')=='manual':
                for key in ('points','box'):label[key]=copy.deepcopy(old.get(key))
        elif old and old.get('editing_state')=='manual':
            label.update({k:copy.deepcopy(old.get(k)) for k in ('editing_state','manual_edits','points','box')})
        manual_draw=self.draft.get('source')=='manual_draw' or (old or {}).get('source')=='manual_draw'
        model=copy.deepcopy(self.draft.get('model_metadata',{})) if manual_draw else {**copy.deepcopy(self.project['model']),**self.draft.get('model_metadata',{})}
        model['single_polygon']=self.single_polygon.isChecked()
        label.update(id=identifier,image_id=self.image['id'],class_id=self.classes.currentData(),status='confirmed',source='manual_draw' if manual_draw else 'interactive',annotation_mode=self.annotation_mode(),model=model,confirmed_at=datetime.now().isoformat())
        from ..label_conflicts import resolve
        try:
            if label.get('box') and label.get('editing_state')!='manual':
                from ..prompt_bounds import clip_geometry
                label['geometry']=clip_geometry(label['geometry'],label['box'])
                if label['geometry'] is None:
                    QMessageBox.information(self,ui_text('labels.confirm.008'),ui_text('prompts.empty_box_result'));return
            result=resolve(label,self.current_labels(),'clip')
            overlaps=result['blocked_ids']
            if result['geometry'] is None:
                QMessageBox.information(self,ui_text('labels.confirm.008'),ui_text('labels.confirm.009'));return
            label['geometry']=result['geometry']
            single=self.single_polygon.isChecked()
            if single:
                from ..single_polygon import select_polygon
                # After subtraction, keep the largest remaining part. Existing
                # labels always win, including labels of a different class.
                label['geometry']=select_polygon(label['geometry'],() if overlaps else self.draft.get('points',[]))
                result['saved_area']=shape(label['geometry']).area
            if overlaps:
                label['model']['overlap_resolution']={k:result[k] for k in ('policy','blocked_ids','original_area','saved_area')}
                label['model']['overlap_resolution']['component_policy']='largest_area' if single else 'keep_all'
        except Exception as e:self.error(str(e));return
        old_index=next((i for i,l in enumerate(self.project['labels']) if l['id']==identifier),len(self.project['labels']))
        from ..label_parts import split_label
        saved=split_label(label,self.draft.get('display_ids',[]))
        for part in saved:part['class_id']=self.draft.get('part_classes',{}).get(part['id'],part['class_id'])
        removed_ids={l['id'] for l in result['removed']}
        history=[(identifier,old,old_index)]+[(l['id'],copy.deepcopy(l),i) for i,l in enumerate(self.project['labels']) if l['id'] in removed_ids]
        remaining=[l for l in self.project['labels'] if l['id']!=identifier and l['id'] not in removed_ids]
        history.extend((part['id'],None,len(remaining)+i) for i,part in enumerate(saved) if i)
        self.flush_label_history()
        self.project['labels']=remaining+saved;self.label_undo.append(history);self.label_redo=[];self.clear_draft();self.selected_id=identifier;self.selected_ids={part['id'] for part in saved}
        self.pending_review=review_position;self.refresh_labels();self.label_presenter.reveal(identifier);self.mark_dirty();self.autosave();self.log_message(ui_text('labels.confirm.006')+identifier[:8])



