"""Human polygon editing and its persisted history transaction."""
import copy
from shapely.geometry import shape,mapping,Point,LineString
from shapely.ops import nearest_points
from ..editing_state import manual_label,reshaped_label
from ..raster_snapshot import image_snapshot
from ..ui.text import ui_text


def _crosses_ring(geometry,line,include_holes):
    """A touch or a crossing of different rings cannot reshape a ring."""
    from ..reshape import _intersection_points
    polygon=shape(geometry)
    parts=polygon.geoms if polygon.geom_type=='MultiPolygon' else (polygon,)
    for part in parts:
        rings=[part.exterior,*part.interiors] if include_holes else [part.exterior]
        for ring in rings:
            hits=_intersection_points(line.intersection(LineString(ring.coords)))
            if len(hits)>=2 and max(map(line.project,hits))-min(map(line.project,hits))>max(1.,line.length)*1e-12:
                return True
    return False


def _reshape_sources(originals,image,value,enabled,task,cache=None,cache_epoch=None):
    if not enabled:return {label['id']:label['geometry'] for label in originals}
    from ..smoothing import smooth_batch
    # Keep hidden interior rings: filling is a view option, not a destructive edit.
    return {label['id']:label['geometry'] for label in smooth_batch(originals,value,image,task,cache,cache_epoch)}


def _reshape_deferred_current(window,session,context,stroke,alternate,include_holes,single):
    """Reject a delayed calculation when its edit session or options changed."""
    return (window.reshape_session is session and window.annotation_context()==context
            and session['stroke']==stroke and session['alternate']==alternate and window.raw_view_action.isChecked()
            and (not window.fill_holes.isChecked())==include_holes
            and (window.mode_index==0 and window.single_polygon.isChecked())==single)


class ReshapeWorkflow:
    def visible_reshape_geometries(self,originals):
        """Snapshot the actual scene outlines without running another smoothing job."""
        visible={}
        for label in originals:
            item=self.view.overlay_records.get(label['id'])
            geometry=getattr(item,'geometry_value',None) if item is not None else None
            visible[label['id']]=geometry if geometry is not None else label['geometry']
        return visible

    def reshape_error(self,session,message,*,log=True):
        session['error']=message
        if log:self.log_message(message)
        self.statusBar().report_error('重塑未完成：'+str(message),source='reshape')

    def model_prompts_locked(self,include_reshape=True):
        if include_reshape and self.reshape_session is not None:return True
        if self.draft.get('editing_state')=='manual':return True
        # Selection alone is not an edit session. A saved manual label must not
        # prevent starting a new target with the point/box tools.
        identifier=self.draft.get('base_id')
        return manual_label(next((l for l in self.project['labels'] if l['id']==identifier),None))

    def interrupt_reshape(self):
        """Discard a pending line before an operation changes its context."""
        if self.reshape_session is not None:
            self.leave_reshape();self.view.reshape_picking=self.view.mode=='reshape'
            self.mark_dirty()

    def begin_reshape(self,auto=False):
        from ..operation_state import interaction_locked
        if interaction_locked(self):return
        if self.foreground_task_active() or not self.image or not self.raw_view_action.isChecked():return
        from ..tool_state import has_unsaved_annotation,has_reshape_target,reshape_presentation_pending
        if reshape_presentation_pending(self):return
        if not has_reshape_target(self):
            self.mode_actions[self.view.selected_mode].setChecked(True)
            if has_unsaved_annotation(self.draft):self.statusBar().showMessage('请先保存或取消未完成的标注。',4000)
            return
        if self.reshape_session is not None:
            self.set_tool('reshape');return
        if auto:
            self.reshape_session={'label':{'id':'__stroke'},'target':'auto','context':self.annotation_context(),'stroke':[],'alternate':False,'preview':None}
            self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview()
            self.view.clear_reshape();self.activate_tool('reshape')
            self.refresh_labels();self.update_controls();self.view.setFocus();return
        label=self.selected_label()
        if label is None:
            self.view.reshape_picking=True;self.view.reshape_enabled=True
            self.set_tool('reshape');self.update_controls();self.view.setFocus()
            return
        elif self.draft_modified():
            self.log_message(ui_text('reshape.finish_draft'));return
        self.clear_draft()
        self.selected_id=None;self.selected_ids.clear()
        self.reshape_session={'label':copy.deepcopy(label),'target':'label','context':self.annotation_context(),'stroke':[],'alternate':False,'preview':None}
        self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview()
        self.view.reshape_enabled=True;self.view.clear_reshape();self.activate_tool('reshape')
        self.refresh_labels();self.update_controls();self.view.setFocus()

    def pick_reshape_target(self,identifier):
        if not self.view.reshape_picking or self.foreground_task_active() or self.reshape_session is not None:return
        self.select_label(identifier);self.begin_reshape()

    def reshape_current(self,session):
        return next((label for label in self.current_labels() if label['id']==session['label']['id']),None)

    def add_reshape_point(self,x,y):
        from ..tool_state import reshape_presentation_pending
        if reshape_presentation_pending(self):return
        if self.reshape_session is None and self.view.mode=='reshape':self.begin_reshape(auto=True)
        session=self.reshape_session
        if not session or self.foreground_task_active() or not self.raw_view_action.isChecked():return
        # Only endpoint snapping to this label; no imagery/shoreline inference.
        stroke=session['stroke']
        if len(stroke)>=8192:self.reshape_error(session,ui_text('reshape.too_many_points'));return
        if not stroke and session.get('target')!='auto':
            from ..reshape import editable_boundary
            boundary=editable_boundary(session['label']['geometry'],not self.fill_holes.isChecked());point=Point(x,y);closest=nearest_points(boundary,point)[0]
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
        from ..tool_state import reshape_presentation_pending
        if reshape_presentation_pending(self):return
        from ..tool_state import has_unsaved_annotation
        if session.get('target')=='draft' or has_unsaved_annotation(self.draft):
            self.statusBar().showMessage('请先保存或取消未完成的标注。',4000);return
        if session.get('target')=='auto':self.finish_auto_reshape(session);return
        from ..reshape import editable_boundary
        end=Point(*session['stroke'][-1]);closest=nearest_points(editable_boundary(session['label']['geometry'],not self.fill_holes.isChecked()),end)[0]
        if closest.distance(end)*abs(self.view.transform().m11())<=7:
            session['stroke'][-1]=[closest.x,closest.y];self.view.set_reshape_stroke(session['stroke'])
        from ..reshape import reshape_raster
        label=session['label'];context=self.annotation_context();stroke=copy.deepcopy(session['stroke']);alternate=session['alternate']
        originals=[{'id':l['id'],'status':l['status'],'geometry':l['geometry']} for l in self.current_labels()]
        blockers=[l['geometry'] for l in originals if l['id']!=label['id'] and l['status']=='confirmed']
        image=image_snapshot(self.image);single=self.mode_index==0 and self.single_polygon.isChecked();include_holes=not self.fill_holes.isChecked()
        from ..smoothing import settings
        config=settings(self.project,self.annotation_mode())
        cache=self.smoother.geometry_cache;cache_epoch=cache.snapshot()
        visible=self.visible_reshape_geometries(originals)
        result_task=[None]
        self.view.reshape_enabled=False;session['preview']=None;session.pop('error',None)
        def work(task):
            geometry=label['geometry'];line=LineString(stroke);reference=None
            if config['enabled'] and not _crosses_ring(geometry,line,include_holes) and _crosses_ring(visible[label['id']],line,include_holes):
                displayed=_reshape_sources(originals,image,config['value'],True,task,cache,cache_epoch).get(label['id'],geometry)
                if _crosses_ring(displayed,line,include_holes):reference=displayed
            kwargs={'include_holes':include_holes}
            kwargs['pixel_grid']=True
            if reference is not None:kwargs['reference']=reference
            result=reshape_raster(image,geometry,stroke,blockers,None,single,alternate,task,**kwargs)
            return result
        def done(result):
            if self.reshape_session is not session or self.annotation_context()!=context:
                self.task_outcome='cancelled';return
            if self.task and self.task.cancel_event.is_set():return
            current=self.reshape_current(session)
            if not current or current['geometry']!=label['geometry']:
                self.task_outcome='failed';self.reshape_error(session,'标签已变化，请重新重塑。');return
            # Task completion stages this result and removes the construction line.
            result_task[0]=self.task
            session['preview']=result
        def failed(message):
            if self.reshape_session is session:
                session['preview']=None
                if self.task_outcome!='cancelled':
                    from ..error_messages import user_message
                    self.reshape_error(session,user_message(message),log=False)
                self.redraw()
        def completed():
            pending=session.get('_pending_prefetch')
            if pending is not None and pending is not self.pending_prefetch_work:
                session.pop('_pending_prefetch',None)
            if self.closing or result_task[0] and result_task[0].cancel_event.is_set():return
            if self.reshape_session is session and session.get('preview'):return self.commit_reshape()
        previous_pending=self.pending_prefetch_work
        self.run(ui_text('reshape.processing'),work,done,kind='reshape',on_error=failed,on_finished=completed,
                 deferred_valid=lambda:_reshape_deferred_current(self,session,context,stroke,alternate,include_holes,single))
        if self.pending_prefetch_work is not None and self.pending_prefetch_work is not previous_pending:
            session['_pending_prefetch']=self.pending_prefetch_work

    def finish_auto_reshape(self,session):
        from ..tool_state import has_unsaved_annotation
        if has_unsaved_annotation(self.draft):
            self.statusBar().showMessage('请先保存或取消未完成的标注。',4000);return
        from ..reshape import reshape_geometry,validate_reshape_source,ReshapeNoChange
        # Confirmed geometries are immutable values; editing replaces them.
        # Snapshot only the fields used by the worker rather than copying all
        # contours, model metadata and history on the GUI thread.
        originals=[{'id':label['id'],'status':label['status'],'geometry':label['geometry']} for label in self.current_labels()]
        image=image_snapshot(self.image);stroke=copy.deepcopy(session['stroke']);alternate=session['alternate']
        single=self.mode_index==0 and self.single_polygon.isChecked();include_holes=not self.fill_holes.isChecked();context=self.annotation_context()
        from ..smoothing import settings
        config=settings(self.project,self.annotation_mode())
        cache=self.smoother.geometry_cache;cache_epoch=cache.snapshot()
        visible=self.visible_reshape_geometries(originals)
        result_holder=[];result_task=[None]
        self.view.reshape_enabled=False;session.pop('error',None)
        def work(task):
            # Evaluate the actual visible outline as well as the underlying
            # geometry; smoothing can move a boundary across the drawn line.
            from ..project_validation import validate_stroke
            validate_stroke(stroke)
            line=LineString(stroke);targets=[]
            if not line.is_simple or not line.is_valid or line.length==0:
                raise ValueError('重塑线无效或自相交，请调整编辑线。')
            displayed=None
            for label in originals:
                task.check()
                raw=label['geometry'];shown=visible[label['id']]
                if _crosses_ring(shown,line,include_holes):
                    reference=None
                    if not _crosses_ring(raw,line,include_holes):
                        if displayed is None:displayed=_reshape_sources(originals,image,config['value'],config['enabled'],task,cache,cache_epoch)
                        reference=displayed[label['id']]
                        if not _crosses_ring(reference,line,include_holes):continue
                    targets.append(('label',label,reference))
            if not targets:return [],[]
            validate_reshape_source(image,task)
            from collections import deque
            target_map={label['id']:(target,label,reference) for target,label,reference in targets}
            pending=deque(target_map);queued=set(pending);results={};blocked={};seen={};unchanged=None
            attempts=0;limit=max(len(targets),min(4096,max(64,len(targets)*16)))
            while pending:
                task.check();attempts+=1
                if attempts>limit:raise ValueError('批量重塑未能收敛，请分段处理。')
                identifier=pending.popleft();queued.remove(identifier)
                target,label,reference=target_map[identifier]
                blockers=[results.get(l['id'],l)['geometry'] for l in originals
                          if l['id']!=identifier and l['status']=='confirmed']
                kwargs={'include_holes':include_holes}
                kwargs['pixel_grid']=True
                if reference is not None:kwargs['reference']=reference
                previous=shape(results[identifier]['geometry']) if identifier in results else shape(label['geometry'])
                try:result=reshape_geometry(image,label['geometry'],stroke,blockers,None,single,alternate,task,**kwargs)
                except ReshapeNoChange as error:
                    if identifier in results:raise ValueError('批量重塑结果发生冲突，请分段处理。') from error
                    unchanged=error;blocked[identifier]=getattr(error,'blocked_geometry',None);continue
                blocked[identifier]=result.get('_blocked_geometry')
                current=shape(result['geometry']);original=shape(label['geometry'])
                if identifier in results:
                    if previous.equals(current):continue
                    if (previous.difference(original).difference(current).area>0 or
                        original.difference(previous).intersection(current).area>0):
                        raise ValueError('批量重塑结果发生冲突，请分段处理。')
                signature=current.wkb
                if signature in seen.setdefault(identifier,set()):raise ValueError('批量重塑未能收敛，请分段处理。')
                seen[identifier].add(signature);results[identifier]=result
                released=previous.difference(current)
                if not released.is_empty:
                    for other,area in blocked.items():
                        if other!=identifier and area and other not in queued and released.intersection(shape(area)).area>0:
                            pending.append(other);queued.add(other)
            if not results and unchanged is not None:raise unchanged
            validate_reshape_source(image,task)
            return [(target_map[i][0],target_map[i][1]) for i in results],list(results.values())
        def done(value):
            if self.reshape_session is session and self.annotation_context()==context:
                targets,results=value
                if not targets:
                    self.task_outcome='failed';self.reshape_error(session,'重塑线未穿过标注边界，请调整编辑线。');return
                result_task[0]=self.task;result_holder.append((targets,results))
            else:self.task_outcome='cancelled'
        def failed(message):
            if self.task_outcome!='cancelled' and not self.closing and self.reshape_session is session and self.annotation_context()==context:
                from ..error_messages import user_message
                self.reshape_error(session,user_message(message),log=False);self.update_controls()
        def completed():
            pending=session.get('_pending_prefetch')
            if pending is not None and pending is not self.pending_prefetch_work:
                session.pop('_pending_prefetch',None)
            if self.closing or result_task[0] and result_task[0].cancel_event.is_set():return
            if self.reshape_session is not session or self.annotation_context()!=context or not result_holder:return
            targets,results=result_holder[0];return self.apply_reshape_results(session,targets,results)
        previous_pending=self.pending_prefetch_work
        started=self.run(ui_text('reshape.processing'),work,done,kind='reshape',on_error=failed,on_finished=completed,
                         deferred_valid=lambda:_reshape_deferred_current(self,session,context,stroke,alternate,include_holes,single))
        if self.pending_prefetch_work is not None and self.pending_prefetch_work is not previous_pending:
            session['_pending_prefetch']=self.pending_prefetch_work
        if not started:self.update_controls()

    def commit_reshape(self):
        session=self.reshape_session
        if not session or self.foreground_task_active() or not session['preview']:return False
        current=self.reshape_current(session)
        if not current or self.annotation_context()!=session['context'] or current['geometry']!=session['label']['geometry']:
            self.reshape_error(session,'标签已变化，请重新重塑。');return False
        return self.apply_reshape_results(session,[(session['target'],current)],[session['preview']])

    def apply_reshape_results(self,session,targets,results):
        """Commit saved targets together while preserving any unrelated draft."""
        from ..label_conflicts import resolve,assert_no_overlaps
        from ..label_parts import split_label
        from ..tool_state import has_unsaved_annotation
        if has_unsaved_annotation(self.draft) or any(target!='label' for target,_ in targets):
            self.reshape_error(session,'请先保存或取消未完成的标注。');return False
        if len(targets)!=len(results):raise ValueError('重塑结果数量不一致。')
        originals=self.current_labels();by_id={label['id']:label for label in originals}
        replacements={};history=[];target_ids={label['id'] for _,label in targets}
        try:
            for (target,label),result in zip(targets,results):
                from ..reshape_validity import repair_reshape_geometry
                repaired=repair_reshape_geometry(result['geometry']);geometry=mapping(repaired)
                if self.single_polygon.isChecked() and repaired.geom_type=='MultiPolygon':
                    from ..single_polygon import select_polygon
                    geometry=select_polygon(geometry)
                result=dict(result,geometry=geometry)
                current=by_id.get(label['id'])
                if not current or current['geometry']!=label['geometry']:raise ValueError('标签已变化，请重新重塑。')
                replacement=reshaped_label(current,result)
                # Other edited labels are represented by their final results,
                # not their superseded original outlines.
                blockers=[item for item in originals if item['id'] not in target_ids]
                geometry=resolve(replacement,blockers,'clip')['geometry']
                if geometry is None:raise ValueError('重塑后目标为空，请调整编辑线。')
                replacement['geometry']=geometry;parts=split_label(replacement)
                replacements[current['id']]=parts
                index=next(i for i,item in enumerate(self.project['labels']) if item['id']==current['id'])
                history.append((current['id'],copy.deepcopy(current),index))
                history.extend((part['id'],None,index+i) for i,part in enumerate(parts[1:],1))
            assert_no_overlaps([part for parts in replacements.values() for part in parts])
        except Exception as error:
            session['preview']=None;self.reshape_error(session,str(error));self.update_controls();return False
        self.retain_reshape_smoothing(replacements)
        self.record_label_operation(history)
        if replacements:
            self.project['labels']=[part for item in self.project['labels'] for part in replacements.get(item['id'],[item])]
        self.leave_reshape();self.refresh_labels();self.mark_dirty();self.autosave();return True

    def cancel_reshape(self):
        if self.reshape_session is None and not self.view.reshape_picking:return
        self.leave_reshape();self.view.reshape_picking=self.view.mode=='reshape';self.refresh_labels();self.mark_dirty()

    def confirm_reshape_batch(self):
        """Validate the whole batch before publishing one undoable transaction."""
        from datetime import datetime
        from ..domain import uid
        from ..label_conflicts import resolve
        from ..label_parts import split_resolved_label
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
                original_geometry=label['geometry']
                result=resolve(label,blockers,'clip')
                if result['geometry'] is None:raise ValueError('重塑后目标为空，请调整编辑线。')
                label['geometry']=result['geometry'];parts=split_resolved_label(label,original_geometry,draft.get('display_ids',[]),draft.get('part_classes'))
                index=next((i for i,l in enumerate(self.project['labels']) if l['id']==identifier),len(self.project['labels']))
                history.append((identifier,copy.deepcopy(old),index))
                history.extend((part['id'],None,len(self.project['labels'])+len(updates)+i) for i,part in enumerate(parts) if part['id']!=identifier)
                updates.extend(parts)
        except Exception as error:self.log_message(str(error));return
        ids={identifier for identifier,_,_ in history}
        self.flush_label_history()
        self.project['labels']=[l for l in self.project['labels'] if l['id'] not in ids]+updates
        self.label_undo.append(history);self.label_redo=[];self.clear_draft()
        self.refresh_labels();self.mark_dirty();self.autosave()

    def leave_reshape(self):
        session=self.reshape_session
        if session and session.get('_pending_prefetch') is self.pending_prefetch_work:
            self.pending_prefetch_work=None
        if self.task and self.task_kind=='reshape':self.task.cancel()
        self.reshape_session=None;self.view.reshape_picking=False;self.view.clear_reshape();self.view.reshape_enabled=False

    def update_reshape_controls(self,controls):
        session=self.reshape_session;active=session is not None;busy=self.foreground_task_active();locked=self.model_prompts_locked(include_reshape=False)
        self.reshape_cancel_shortcut.setEnabled(active)
        shortcut='' if active else 'Esc'
        if self.new_target_button.shortcut().toString()!=shortcut:self.new_target_button.setShortcut(shortcut)
        from ..tool_state import has_reshape_target,reshape_presentation_pending
        reshape_enabled=not busy and self.raw_view_action.isChecked() and has_reshape_target(self) and not reshape_presentation_pending(self)
        if self.view.mode=='reshape' and not active:self.view.reshape_enabled=reshape_enabled
        controls.enable(self.editor_group,not busy)
        if self.draft.get('reshape_batch'):controls.enable(self.classes,False)
        if active:
            self.view.reshape_enabled=reshape_enabled
            controls.enable(self.undo_prompt_action,not busy and bool(session['stroke'] or self.label_undo or self.prompt_undo));controls.enable(self.redo_prompt_action,not busy and bool(session.get('redo_stroke') or self.label_redo or self.prompt_redo))
        if locked:
            for key in ('positive','negative','box','select_points'):controls.enable(self.mode_actions[key],False)
            for control in (self.apply_button,self.auto_apply,self.single_polygon,self.clear_points_button,self.delete_points_button):controls.enable(control,False)
        else:
            controls.enable(self.auto_apply,not busy)
        controls.enable(self.fill_holes,not busy)
        from ..tool_state import available_tools
        for mode,enabled in available_tools(self).items():controls.enable(self.mode_actions[mode],enabled)
