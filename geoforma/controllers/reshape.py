"""Human raster editing and its persisted history transaction."""
import copy
from shapely.geometry import shape,Point,LineString
from shapely.ops import nearest_points
from ..editing_state import manual_label,label_draft,stage_manual_edit
from ..raster_snapshot import image_snapshot
from ..ui.text import ui_text


class ReshapeWorkflow:
    def reshape_error(self,session,message,*,log=True):
        session['error']=message
        if log:self.log_message(message)

    def model_prompts_locked(self,include_reshape=True):
        if include_reshape and self.reshape_session is not None:return True
        if self.reshape_session is not None and manual_label(self.reshape_session['label']):return True
        if self.draft.get('editing_state')=='manual':return True
        # Selection alone is not an edit session. A saved manual label must not
        # prevent starting a new target with the point/box tools.
        identifier=self.draft.get('base_id')
        return manual_label(next((l for l in self.project['labels'] if l['id']==identifier),None))

    def begin_reshape(self,auto=False):
        from ..operation_state import interaction_locked
        if interaction_locked(self):return
        if self.foreground_task_active() or not self.image or not self.raw_view_action.isChecked():return
        if self.reshape_session is not None:
            self.set_tool('reshape');return
        if auto:
            self.reshape_session={'label':{'id':'__stroke'},'target':'auto','context':self.annotation_context(),'stroke':[],'alternate':False,'preview':None}
            self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview()
            self.view.clear_reshape();self.activate_tool('reshape')
            self.refresh_labels();self.update_controls();self.view.setFocus();return
        label=self.selected_label()
        draft_target=bool(self.draft.get('geometry'))
        if draft_target:
            if self.draft.get('pending'):return
            label={**copy.deepcopy(self.draft),'id':self.draft.get('base_id') or '__draft','image_id':self.image['id'],'status':'confirmed'}
        elif label is None:
            self.view.reshape_picking=True;self.view.reshape_enabled=True
            self.set_tool('reshape');self.update_controls();self.view.setFocus()
            return
        elif self.draft_modified():
            self.log_message(ui_text('reshape.finish_draft'));return
        if not draft_target:
            self.clear_draft()
        self.selected_id=None;self.selected_ids.clear()
        self.reshape_session={'label':copy.deepcopy(label),'target':'draft' if draft_target else 'label','context':self.annotation_context(),'stroke':[],'alternate':False,'preview':None}
        self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview()
        self.view.reshape_enabled=True;self.view.clear_reshape();self.activate_tool('reshape')
        self.refresh_labels();self.update_controls();self.view.setFocus()

    def pick_reshape_target(self,identifier):
        if not self.view.reshape_picking or self.foreground_task_active() or self.reshape_session is not None:return
        self.select_label(identifier);self.begin_reshape()

    def reshape_current(self,session):
        if session.get('target')=='draft':
            return self.draft if self.draft.get('geometry')==session['label']['geometry'] else None
        return next((label for label in self.current_labels() if label['id']==session['label']['id']),None)

    def add_reshape_point(self,x,y):
        if self.reshape_session is None and self.view.mode=='reshape':self.begin_reshape(auto=True)
        session=self.reshape_session
        if not session or self.foreground_task_active() or not self.raw_view_action.isChecked():return
        # Only endpoint snapping to this label; no imagery/shoreline inference.
        stroke=session['stroke']
        if len(stroke)>=8192:self.reshape_error(session,ui_text('reshape.too_many_points'));return
        if not stroke and session.get('target')!='auto':
            geometry=shape(session['label']['geometry']);point=Point(x,y);closest=nearest_points(geometry.boundary,point)[0]
            if closest.distance(point)*abs(self.view.transform().m11())<=7:x,y=closest.x,closest.y
        if stroke and stroke[-1]==[x,y]:return
        preview=session.get('preview');stroke.append([x,y]);session['preview']=None;session['redo_stroke']=[];session.pop('error',None)
        self.view.set_reshape_stroke(stroke)
        if preview:self.redraw()
        self.update_controls();self.mark_dirty()

    def undo_reshape_point(self):
        if not self.reshape_session or self.foreground_task_active():return
        if not self.reshape_session['stroke']:return
        preview=self.reshape_session.get('preview');self.reshape_session.setdefault('redo_stroke',[]).append(self.reshape_session['stroke'].pop())
        self.reshape_session['preview']=None;self.reshape_session.pop('error',None);self.view.set_reshape_stroke(self.reshape_session['stroke'])
        if preview:self.redraw()
        self.update_controls();self.mark_dirty()

    def redo_reshape_point(self):
        session=self.reshape_session
        if not session or self.foreground_task_active() or not session.get('redo_stroke'):return
        session['stroke'].append(session['redo_stroke'].pop());session['preview']=None;session.pop('error',None)
        self.view.set_reshape_stroke(session['stroke']);self.update_controls();self.mark_dirty()

    def reshape_alternate(self):
        if not self.reshape_session or self.foreground_task_active():return
        self.reshape_session['alternate']=not self.reshape_session['alternate'];self.mark_dirty();self.update_controls()

    def finish_reshape(self):
        session=self.reshape_session
        if not session or self.foreground_task_active() or len(session['stroke'])<2:return
        if session.get('target')=='auto':self.finish_auto_reshape(session);return
        end=Point(*session['stroke'][-1]);closest=nearest_points(shape(session['label']['geometry']).boundary,end)[0]
        if closest.distance(end)*abs(self.view.transform().m11())<=7:
            session['stroke'][-1]=[closest.x,closest.y];self.view.set_reshape_stroke(session['stroke'])
        from ..reshape import reshape_raster
        label=session['label'];context=self.annotation_context();stroke=copy.deepcopy(session['stroke']);alternate=session['alternate']
        blockers=[copy.deepcopy(l['geometry']) for l in self.current_labels() if l['id']!=label['id'] and l['status']=='confirmed']
        image=image_snapshot(self.image);single=self.mode_index==0 and self.single_polygon.isChecked();fill=self.fill_holes.isChecked()
        result_task=[None]
        self.view.reshape_enabled=False;session['preview']=None;session.pop('error',None)
        def work(task):
            result=reshape_raster(image,label['geometry'],stroke,blockers,None,single,label.get('points') or [],alternate,task)
            if fill:
                from ..hole_filling import fill_reshape_result
                result=fill_reshape_result(result,blockers)
            return result
        def done(result):
            if self.reshape_session is not session or self.annotation_context()!=context:return
            if self.task and self.task.cancel_event.is_set():return
            current=self.reshape_current(session)
            if not current or current['geometry']!=label['geometry']:return
            # Task completion stages this result and removes the construction line.
            result_task[0]=self.task
            session['preview']=result
        def failed(message):
            if self.reshape_session is session:
                from ..error_messages import user_message
                session['preview']=None;self.reshape_error(session,user_message(message),log=False);self.redraw()
        def completed():
            if self.closing or result_task[0] and result_task[0].cancel_event.is_set():return
            if self.reshape_session is session and session.get('preview'):self.commit_reshape()
        self.run(ui_text('reshape.processing'),work,done,kind='reshape',on_error=failed,on_finished=completed)

    def finish_auto_reshape(self,session):
        from ..reshape import reshape_raster
        line=LineString(session['stroke']);base=self.draft.get('base_id');targets=[]
        # Table selection never determines the edit target. Only displayed
        # labels participate, using their canonical source geometry.
        for label in self.presentation_labels():
            if label['id']!=base and line.intersects(shape(label['geometry']).boundary):
                targets.append(('label',copy.deepcopy(label)))
        if self.draft.get('geometry') and line.intersects(shape(self.draft['geometry']).boundary):
            targets.append(('draft',{**copy.deepcopy(self.draft),'id':base or '__draft','image_id':self.image['id'],'status':'confirmed'}))
        targets.sort(key=lambda item:item[0]!='draft')
        if not targets:
            self.reshape_error(session,'重塑线未穿过标注边界，请调整编辑线。');self.update_controls();return
        if self.draft.get('reshape_batch'):
            self.reshape_error(session,ui_text('reshape.finish_draft'));self.update_controls();return
        image=image_snapshot(self.image);stroke=copy.deepcopy(session['stroke']);alternate=session['alternate']
        single=self.mode_index==0 and self.single_polygon.isChecked();fill=self.fill_holes.isChecked();context=self.annotation_context()
        originals=copy.deepcopy(self.current_labels());result_holder=[];result_task=[None]
        self.view.reshape_enabled=False;session.pop('error',None)
        def work(task):
            outputs=[]
            for target,label in targets:
                task.check()
                blockers=[l['geometry'] for l in originals if l['id']!=label['id'] and l['status']=='confirmed']
                blockers.extend(result['geometry'] for result in outputs)
                result=reshape_raster(image,label['geometry'],stroke,blockers,None,single,label.get('points') or [],alternate,task)
                if fill:
                    from ..hole_filling import fill_reshape_result
                    result=fill_reshape_result(result,blockers)
                outputs.append(result)
            return outputs
        def done(results):
            if self.reshape_session is session and self.annotation_context()==context:
                result_task[0]=self.task;result_holder.extend(results)
        def failed(message):
            self.log_message(message)
            if self.reshape_session is session:
                from ..error_messages import user_message
                self.reshape_error(session,user_message(message),log=False);self.update_controls()
        def completed():
            if self.closing or result_task[0] and result_task[0].cancel_event.is_set():return
            if self.reshape_session is not session or not result_holder:return
            self.apply_reshape_results(session,targets,result_holder)
        self.run(ui_text('reshape.processing'),work,done,kind='reshape',on_error=failed,on_finished=completed)

    def commit_reshape(self):
        session=self.reshape_session
        if not session or self.foreground_task_active() or not session['preview']:return
        current=self.reshape_current(session)
        if not current or self.annotation_context()!=session['context'] or current['geometry']!=session['label']['geometry']:return
        self.apply_reshape_results(session,[(session['target'],current)],[session['preview']])

    def apply_reshape_results(self,session,targets,results):
        """Commit saved targets together while preserving any unrelated draft."""
        from ..label_conflicts import resolve
        from ..label_parts import split_label
        if len(targets)!=len(results):raise ValueError('重塑结果数量不一致。')
        originals=self.current_labels();by_id={label['id']:label for label in originals}
        replacements={};history=[];updated_draft=None
        try:
            for (target,label),result in zip(targets,results):
                if target=='draft':
                    if self.draft.get('geometry')!=label.get('geometry'):raise ValueError('未保存轮廓已变化，请重新重塑。')
                    updated_draft=stage_manual_edit(self.draft,result);continue
                current=by_id.get(label['id'])
                if not current or current['geometry']!=label['geometry']:raise ValueError('标签已变化，请重新重塑。')
                staged=stage_manual_edit(label_draft(current,self.classes.currentData()),result)
                replacement=copy.deepcopy(current)
                for key in ('_bounds','_render_path','_source_geometry','_source_path','raw_geometry','source_geometry','smoothing_applied'):
                    replacement.pop(key,None)
                replacement.update(geometry=staged['geometry'],editing_state='manual',manual_edits=staged['manual_edits'],edge=False)
                blockers=[item for item in originals if item['id']!=current['id']]
                blockers.extend(part for parts in replacements.values() for part in parts)
                geometry=resolve(replacement,blockers,'clip')['geometry']
                if geometry is None:raise ValueError('重塑后目标为空，请调整编辑线。')
                replacement['geometry']=geometry;parts=split_label(replacement)
                replacements[current['id']]=parts
                index=next(i for i,item in enumerate(self.project['labels']) if item['id']==current['id'])
                history.append((current['id'],copy.deepcopy(current),index))
                history.extend((part['id'],None,index+i) for i,part in enumerate(parts[1:],1))
        except Exception as error:
            session['preview']=None;self.reshape_error(session,str(error));self.update_controls();return
        self.retain_reshape_smoothing(replacements,updated_draft)
        self.record_label_operation(history)
        if replacements:
            self.project['labels']=[part for item in self.project['labels'] for part in replacements.get(item['id'],[item])]
        if updated_draft is not None:self.draft=updated_draft
        self.leave_reshape();self.refresh_labels();self.mark_dirty();self.autosave()

    def cancel_reshape(self):
        if self.reshape_session is None and not self.view.reshape_picking:return
        self.leave_reshape();self.view.reshape_picking=self.view.mode=='reshape';self.refresh_labels();self.mark_dirty()

    def confirm_reshape_batch(self):
        """Validate the whole batch before publishing one undoable transaction."""
        from datetime import datetime
        from ..domain import uid
        from ..label_conflicts import resolve
        from ..label_parts import split_label
        if self.foreground_task_active() or self.reshape_session is not None or self.draft.get('pending'):return
        drafts=self.draft.get('reshape_batch',[])
        originals=self.current_labels();updates=[];history=[]
        from ..session_validation import validate_draft
        try:validate_draft(self.draft,self.image['id'],{i['id'] for i in self.project['images']}|{self.image['id']},{l['id']:l for l in self.project['labels']},{c['id'] for c in self.project['classes']})
        except ValueError as error:self.log_message(str(error));return
        try:
            for draft in drafts:
                identifier=draft.get('base_id') or (draft.get('display_ids') or [None])[0] or uid()
                old=next((l for l in originals if l['id']==identifier),None)
                label=copy.deepcopy(old) if old else {'id':identifier,'image_id':self.image['id'],
                    'annotation_mode':self.annotation_mode(),'source':draft.get('source','interactive'),'model':copy.deepcopy(draft.get('model_metadata',{}))}
                label.update({k:copy.deepcopy(draft.get(k)) for k in ('geometry','points','box','window','edge','score','manual_edits')})
                label.update(editing_state='manual',status='confirmed',class_id=draft.get('class_id') or self.classes.currentData(),confirmed_at=datetime.now().isoformat())
                if label['class_id'] is None:raise ValueError('请先选择类别。')
                blockers=[l for l in originals if l['id']!=identifier]+updates
                result=resolve(label,blockers,'clip')
                if result['geometry'] is None:raise ValueError('重塑后目标为空，请调整编辑线。')
                label['geometry']=result['geometry'];parts=split_label(label,draft.get('display_ids',[]))
                for part in parts:part['class_id']=draft.get('part_classes',{}).get(part['id'],part['class_id'])
                index=next((i for i,l in enumerate(self.project['labels']) if l['id']==identifier),len(self.project['labels']))
                history.append((identifier,copy.deepcopy(old),index))
                history.extend((part['id'],None,len(self.project['labels'])+len(updates)+i) for i,part in enumerate(parts) if i)
                updates.extend(parts)
        except Exception as error:self.log_message(str(error));return
        ids={l['id'] for l in updates}
        self.flush_label_history()
        self.project['labels']=[l for l in self.project['labels'] if l['id'] not in ids]+updates
        self.label_undo.append(history);self.label_redo=[];self.clear_draft()
        self.refresh_labels();self.mark_dirty();self.autosave()

    def leave_reshape(self):
        if self.task and self.task_kind=='reshape':self.task.cancel()
        self.reshape_session=None;self.view.reshape_picking=False;self.view.clear_reshape();self.view.reshape_enabled=False

    def update_reshape_controls(self,controls):
        session=self.reshape_session;active=session is not None;busy=self.foreground_task_active();locked=self.model_prompts_locked()
        if self.view.mode=='reshape' and not active:self.view.reshape_enabled=not busy and self.raw_view_action.isChecked()
        self.mode_settings.setCurrentWidget(self.reshape_group if active else self.prompt_group);controls.enable(self.editor_group,not active)
        if self.draft.get('reshape_batch'):controls.enable(self.classes,False)
        if active:
            controls.enable(self.reshape_other_button,not busy and len(session['stroke'])>=2)
            self.reshape_other_button.setChecked(bool(session['alternate']));controls.enable(self.reshape_cancel_button,not busy)
            self.view.reshape_enabled=not busy and self.raw_view_action.isChecked()
            controls.enable(self.images,False);controls.enable(self.labels_table,not busy)
            controls.enable(self.model_button,False);controls.enable(self.import_button,False);controls.enable(self.import_action,False);controls.enable(self.classes_button,False)
            for key in ('new','open'):controls.enable(self.project_actions[key],False)
            controls.enable(self.confirm_button,False);controls.enable(self.delete_button,False);controls.enable(self.delete_action,False);controls.enable(self.undo_label_action,False)
            for control in (self.previous_button,self.next_button,self.classes,self.reprepare_button,self.preprocess_button,self.bands_button,self.crs_button):controls.enable(control,False)
            controls.enable(self.undo_prompt_action,not busy and bool(session['stroke']));controls.enable(self.redo_prompt_action,not busy and bool(session.get('redo_stroke')))
        if locked:
            for key in ('positive','negative','box','select_points'):controls.enable(self.mode_actions[key],False)
            for control in (self.apply_button,self.auto_apply,self.single_polygon,self.fill_holes,self.clear_points_button,self.delete_points_button):controls.enable(control,False)
        else:
            controls.enable(self.auto_apply,not busy)
        from ..tool_state import available_tools
        for mode,enabled in available_tools(self).items():controls.enable(self.mode_actions[mode],enabled)
