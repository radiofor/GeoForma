"""PromptWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy
from shapely.geometry import shape
from ..domain import prompt_window
from ..workflow import best_choice
from ..raster_snapshot import image_snapshot
from ..prompt_bounds import contains_point,bounded_points,clip_geometry
from ..editing_state import draft_snapshot,geometry_history


class PromptWorkflow:
    def fill_holes_changed(self,enabled):
        if getattr(self,'restoring_project',False):return
        self.invalidate_preview();self.mark_dirty()
        self.update_controls()

    def single_polygon_changed(self,enabled):
        if getattr(self,'restoring_project',False):return
        if self.model_prompts_locked():return
        self.invalidate_preview();self.mark_dirty()
        if enabled and self.mode_index==0 and self.draft.get('geometry'):
            from ..single_polygon import constrain_choice
            selected=constrain_choice(self.draft,self.draft.get('points',[]),True,self.draft.get('box'))
            if selected:self.draft.update(geometry=selected['geometry'],pixels=selected['pixels'])
        if self.mode_index==0 and self.draft and (self.draft.get('points') or self.draft.get('box') or self.draft.get('seed_geometry')):self.prompts_changed()
        else:self.refresh_labels()
        self.update_controls()

    def set_tool(self,mode):
        from ..tool_state import available_tools
        if self.draft.get('manual_vertices') and mode not in ('draw_polygon','pan'):
            self.mode_actions[self.view.selected_mode].setChecked(True)
            self.statusBar().showMessage('请先完成或取消正在绘制的多边形。',4000);return
        if not available_tools(self).get(mode,False):
            self.mode_actions[self.view.selected_mode].setChecked(True);return
        leaving=self.reshape_session is not None and mode not in ('reshape','pan')
        if leaving:self.leave_reshape()
        if mode!='reshape':self.view.reshape_picking=False
        self.activate_tool(mode)
        if mode=='draw_polygon':self.statusBar().showMessage('左键添加顶点，右键完成；Backspace 撤回，Esc 取消。',6000)
        if leaving:self.refresh_labels();self.mark_dirty()
        self.update_controls()

    def activate_tool(self,mode):
        self.view.set_mode(mode);self.mode_actions[mode].setChecked(True)
        self.view.reshape_picking=mode=='reshape' and self.reshape_session is None
        self.tool_modes[self.annotation_mode()]=mode

    def restore_tool(self,preferred=None):
        from ..tool_state import restored_tool
        self.activate_tool(restored_tool(preferred,self.view.selected_mode,self.annotation_mode()))
        self.update_controls()


    def draft_modified(self):
        changed_class='initial_class_id' in self.draft and self.draft.get('class_id')!=self.draft['initial_class_id']
        return bool(self.draft and (self.draft.get('pending') or self.draft.get('points') or self.draft.get('box') or self.draft.get('ignore_seed') or changed_class or self.geometry_history()))

    def geometry_snapshot(self):return {'_draft':draft_snapshot(self.draft)}

    def geometry_history(self):return geometry_history(self.prompt_undo,self.prompt_redo)

    def prompt_context(self):return self.geometry_history() or (not self.model_prompts_locked() and bool(self.draft and (self.prompt_undo or self.prompt_redo or self.draft.get('pending') or self.draft.get('points') or self.draft.get('box') or self.draft.get('ignore_seed'))))

    def toggle_raw(self):
        self.view.set_overlay_visibility(self.raw_view_action.isChecked())
        self.update_controls()

    def sync_overlay_visibility_button(self):
        # Project commits block QAction signals, so synchronize its status view too.
        self.visibility_toolbar.widgetForAction(self.raw_view_action).sync_state()

    def reset_prior(self):
        if not self.can_prompt() or not (self.draft.get('points') or self.draft.get('box')):return
        self.push_prompt();self.draft['ignore_seed']=True;self.prompts_changed();self.predict()


    def prompt_snapshot(self):
        return {key:copy.deepcopy(self.draft.get(key)) for key in ('points','box','window','ignore_seed')}

    def push_prompt(self):self.prompt_undo.append(self.prompt_snapshot());self.prompt_redo=[]

    def prompts_changed(self):
        self.prompt_revision+=1
        self.invalidate_preview()
        # Keep the last displayed result, but never confirm it with changed prompts.
        self.draft['pending']=True;self.selected_points.clear();self.draft.pop('logits',None)
        if self.draft.get('box'):
            self.draft['points']=bounded_points(self.draft.get('points',[]),self.draft['box'])
            if self.draft.get('geometry'):self.draft['geometry']=clip_geometry(self.draft['geometry'],self.draft['box'])
        self.update_draft_info();self.refresh_labels();self.mark_dirty()
        if self.auto_apply.isChecked():self.auto_apply_timer.start()

    def auto_apply_changed(self,enabled):
        if enabled and self.draft.get('pending'):self.auto_apply_timer.start()
        if not enabled:self.auto_apply_timer.stop()
        self.update_controls()

    def apply_automatically(self):
        if self.can_apply_current() and self.auto_apply.isChecked() and self.draft.get('pending') and not self.closing:self.predict()

    def prompt_target_available(self):return True

    def can_apply_current(self):
        return not self.model_prompts_locked()

    def prompt_task_busy(self):
        from ..operation_state import background_prefetch
        editable=self.task_kind=='interactive' and self.auto_apply.isChecked()
        return bool(self.task and not editable and not background_prefetch(self))

    def can_prompt(self):
        if self.model_prompts_locked():self.statusBar().showMessage(ui_text('reshape.locked'),3000);return False
        if self.prompt_task_busy():return False
        if not self.raw_view_action.isChecked():self.statusBar().showMessage(ui_text('prompts.can_prompt.005'),2000);return False
        if not self.image or not self.image.get('ready'):self.statusBar().showMessage(ui_text('prompts.can_prompt.006'),3000);return False
        return True

    def add_point(self,x,y,label):
        if not self.can_prompt():return
        if not contains_point(self.draft.get('box'),x,y):
            self.statusBar().showMessage(ui_text('prompts.outside_box'),2000);return
        from ..prompt_bounds import MAX_PROMPT_POINTS
        if len(self.draft.get('points',[]))>=MAX_PROMPT_POINTS:
            self.statusBar().showMessage('单个目标的提示点过多，请先保存当前目标。',4000);return
        if not self.draft.get('base_id'):self.selected_ids.clear();self.selected_id=None
        self.push_prompt();self.draft.setdefault('points',[]).append([x,y,label]);self.prompts_changed()

    def add_box(self,box):
        if not self.can_prompt():return
        if not self.draft.get('base_id'):self.selected_ids.clear();self.selected_id=None
        self.push_prompt();self.draft['box']=list(box);self.draft['window']=None;self.draft.setdefault('points',[]);self.prompts_changed()

    def clear_box(self):
        if self.model_prompts_locked() or self.prompt_task_busy() or not self.draft.get('box'):return
        self.push_prompt();self.draft['box']=None;self.prompts_changed()

    def delete_points(self):
        if self.model_prompts_locked() or self.prompt_task_busy() or not self.selected_points:return
        self.push_prompt();self.draft['points']=[p for i,p in enumerate(self.draft.get('points',[])) if i not in self.selected_points];self.prompts_changed()

    def clear_points(self):
        if not self.can_prompt() or not self.draft.get('points'):return
        self.push_prompt();self.draft['points']=[];self.prompts_changed()

    def stage_expand(self):
        if not self.can_prompt() or not self.draft.get('window'):return
        try:
            points=self.draft.get('points',[]);box=self.draft.get('box')
            if not points and not box and self.draft.get('geometry'):box=list(shape(self.draft['geometry']).bounds)
            window=prompt_window(points,box,self.draft['window'],True);self.push_prompt();self.draft['window']=list(window);self.prompts_changed()
        except Exception as e:self.error(str(e))

    def predict(self,expand=False):
        if self.defer_for_prefetch(lambda:self.predict(expand),allow_prompt_changes=True):return
        if self.task:return
        if not self.can_apply_current():
            self.statusBar().showMessage(ui_text('reshape.locked' if self.model_prompts_locked() else 'prompts.predict.007'),4000);return
        if not self.can_prompt():return
        if expand:self.stage_expand();return
        if not self.draft.get('points') and not self.draft.get('box') and not self.draft.get('seed_geometry'):
            for key in ('geometry','logits','choices','edge','score','feature_key'):self.draft.pop(key,None)
            self.draft['pending']=False;self.refresh_labels();self.update_draft_info();self.update_controls();self.mark_dirty()
            self.log_message(ui_text('prompts.predict.008'));return
        try:
            previous=self.draft.get('window');points=self.draft.get('points',[]);box=self.draft.get('box')
            # An existing contour can supply the extent when expanding.
            selection_box=box or (list(shape(self.draft['geometry']).bounds) if not points and self.draft.get('geometry') else None)
            window=prompt_window(points,selection_box,previous,expand)
            seed=None if self.draft.get('ignore_seed') else self.draft.get('seed_geometry')
            # Recompute from the current prompt set, not stale logits influenced by removed points.
            request={'window':window,'points':copy.deepcopy(points),'box':box or (selection_box if not points else None),'logits':None,
                     'seed':seed,'single_polygon':self.single_polygon.isChecked(),'fill_holes':self.fill_holes.isChecked(),'editing_state':self.draft.get('editing_state','model')}
            # A stale prediction cannot be confirmed while new prompts are pending.
            self.draft['pending']=True;self.redraw();image=image_snapshot(self.image);config=copy.deepcopy(self.project['model'])
            revision=self.prompt_revision;context=self.annotation_context()
            self.run(ui_text('prompts.predict.009'),lambda t:self.service.predict(image,config,request,t),lambda result:self.predicted(result) if revision==self.prompt_revision and context==self.annotation_context() else None,kind='interactive')
        except Exception as e:self.error(str(e))

    def predicted(self,result):
        self.invalidate_preview()
        if result.get('checkpoint'):self.project['model']['checkpoint']=result['checkpoint']
        self.record_runtime(result)
        self.draft['window']=result['window']
        choices=[self.constrain_prediction(choice) for choice in result['choices']]
        self.draft['choices']=[choice for choice in choices if choice is not None];self.draft['pending']=False
        self.draft['model_metadata']=result.get('model_metadata',{});self.draft['feature_key']=result['key']
        index=0 if len(self.draft['choices'])==1 else best_choice(self.draft['choices'],self.draft.get('points',[]))
        if index>=0:self.choose_mask(index)
        else:
            for key in ['geometry','logits','edge','score']:self.draft.pop(key,None)
            self.refresh_labels();self.update_draft_info();self.log_message(ui_text('prompts.predicted.010'))
        self.log_message(ui_text('prompts.predicted.002').format(p0='复用特征' if result['cache_hit'] else '新窗口已编码',p1=result['device'],p2=result['window'][2]))
        self.mark_dirty()

    def choose_mask(self,index):
        choices=self.draft.get('choices',[])
        if 0<=index<len(choices):
            choice=self.constrain_prediction(choices[index])
            if choice is not None:self.draft.update(copy.deepcopy(choice));self.draft['choice']=index;self.update_draft_info();self.refresh_labels();self.mark_dirty()

    def constrain_prediction(self,choice):
        from ..single_polygon import constrain_choice
        return constrain_choice(choice,self.draft.get('points',[]),self.mode_index==0 and self.single_polygon.isChecked(),self.draft.get('box'))

    def update_draft_info(self):
        self.prompt_counters.set_points(self.draft.get('points') or [])
        if self.draft.get('manual_vertices'):text='绘制中 · 右键完成'
        elif self.model_prompts_locked():
            text=ui_text('reshape.draft_changed') if self.draft.get('manual_edits') else ui_text('reshape.locked')
        elif self.draft.get('pending'):text=ui_text('layout.pending')
        elif self.draft.get('geometry'):text=ui_text('layout.unsaved')
        elif self.selected_ids:text=ui_text('layout.selected').format(len(self.selected_ids))
        else:text=ui_text('prompts.update_draft_info.011')
        self.edit_status.setText(text)

    def clear_draft(self):
        if self.reshape_session is not None:self.cancel_reshape();return
        drawing='manual_vertices' in self.draft
        if self.model_prompts_locked():self.selected_ids.clear();self.selected_id=None
        self.prompt_revision+=1;self.auto_apply_timer.stop()
        self.invalidate_preview()
        if self.foreground_task_active():return
        self.flush_label_history()
        self.draft={};self.prompt_undo=[];self.prompt_redo=[];self.selected_points.clear();self.update_draft_info();self.refresh_labels();self.mark_dirty()
        if drawing:self.view.clear_reshape()
        if self.view.mode=='reshape':self.view.reshape_picking=True

    def restore_draft(self,draft):
        self.draft.update(copy.deepcopy(draft));self.draft['points']=self.draft.get('points') or [];self.prompts_changed()

    def restore_geometry_history(self,source,destination):
        if self.reshape_session is not None or self.prompt_task_busy() or not source or '_draft' not in source[-1]:return False
        entry=source.pop();reverse=self.geometry_snapshot()
        if '_label_entries' in entry:reverse['_label_entries']=self.restore_label_entries(entry['_label_entries'])
        destination.append(reverse);self.draft=copy.deepcopy(entry['_draft'])
        self.prompt_revision+=1;self.auto_apply_timer.stop();self.invalidate_preview();self.selected_points.clear()
        category=self.draft.get('class_id')
        if category is not None:
            blocked=self.classes.blockSignals(True);self.classes.setCurrentIndex(self.classes.findData(category));self.classes.blockSignals(blocked)
        self.sync_manual_polygon()
        self.update_draft_info();self.refresh_labels();self.mark_dirty()
        return True

    def undo_prompt(self):
        if self.restore_geometry_history(self.prompt_undo,self.prompt_redo):return
        if not self.model_prompts_locked() and self.prompt_undo and not self.prompt_task_busy():self.prompt_redo.append(self.prompt_snapshot());self.restore_draft(self.prompt_undo.pop())

    def redo_prompt(self):
        if self.restore_geometry_history(self.prompt_redo,self.prompt_undo):return
        if not self.model_prompts_locked() and self.prompt_redo and not self.prompt_task_busy():self.prompt_undo.append(self.prompt_snapshot());self.restore_draft(self.prompt_redo.pop())

