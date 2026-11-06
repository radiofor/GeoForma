"""ControlState responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
from ..domain import digest
from ..theme import set_tone
from ..ui.control_update import ControlUpdate


class ControlState:
    def update_controls(self):
        controls=ControlUpdate()
        from ..operation_state import interaction_locked,can_browse,background_prefetch
        locked=interaction_locked(self)
        browse=can_browse(self)
        physical_busy=self.task is not None or locked
        busy=(self.task is not None and not background_prefetch(self)) or locked;has=self.image is not None;ready=bool(has and self.image.get('ready',False))
        controls.enable(self.project_actions['recover'],not busy and not self.autosave_task and not self.project_path and not self.project['images'] and not self.project['labels'] and not self.project.get('references') and self.previous_work() is not None)
        controls.enable(self.labels_table,not locked)
        controls.enable(self.project_actions['save'],not locked and self.project_path is None)
        for key in ('select','pan'):controls.enable(self.mode_actions[key],not busy)
        controls.enable(self.single_polygon,not busy)
        controls.enable(self.fill_holes,not busy)
        for action in self.actions_to_lock:controls.enable(action,not physical_busy)
        controls.enable(self.import_button,not physical_busy)
        controls.enable(self.images,browse or self.task is not None and self.task_kind=='reshape' and not locked)
        controls.enable(self.model_button,not physical_busy)
        controls.enable(self.import_reference_button,not physical_busy)
        self.sync_reference_buttons()
        for button in [self.bands_button,self.crs_button]:controls.enable(button,has and not physical_busy)
        controls.enable(self.fit_action,has and not locked);controls.enable(self.native_zoom_action,has and not locked)
        controls.enable(self.raw_view_action,not locked)
        controls.enable(self.reprepare_button,has and not physical_busy)
        self.refresh_export_crs();controls.enable(self.export_crs_input,not busy and self.export_kind.currentData()!='.geojson')
        controls.enable(self.export_kind,not busy)
        self.refresh_export_label_field();controls.enable(self.export_label_field_input,not busy)
        controls.enable(self.preprocess_button,has and not physical_busy)
        state=self.image.get('preparation_state') if has else None
        controls.enable(self.confirm_button,bool(self.draft.get('geometry')) and not self.draft.get('pending',False) and not busy and self.classes.currentData() is not None)
        controls.enable(self.classes_button,not busy)
        controls.enable(self.classes,not busy)
        selected_label=self.selected_label() if not self.draft else None
        saved_selection=selected_label and selected_label['status']=='confirmed'
        self.confirm_button.setText('已保存' if saved_selection else ui_text('action.confirm'))
        eligible=self.can_apply_current()
        controls.enable(self.apply_button,ready and not busy and eligible and not self.auto_apply.isChecked() and bool(self.draft.get('pending') or self.draft.get('points') or self.draft.get('box')))
        self.apply_button.setToolTip(ui_text('control_state.update_controls.009') if not eligible else ui_text('control_state.update_controls.010'))
        prompt_busy=self.prompt_task_busy()
        controls.enable(self.delete_points_button,bool(self.selected_points) and not prompt_busy)
        controls.enable(self.new_target_button,bool(self.draft) and not busy)
        controls.enable(self.clear_points_button,eligible and ready and not prompt_busy and bool(self.draft.get('points')))
        controls.enable(self.undo_prompt_action,not prompt_busy and bool(self.prompt_undo if self.prompt_context() else self.label_undo))
        controls.enable(self.redo_prompt_action,not prompt_busy and bool(self.prompt_redo if self.prompt_context() else self.label_redo))
        controls.enable(self.undo_label_action,bool(self.label_undo or self.prompt_undo and '_label_entries' in self.prompt_undo[-1]) and not busy)
        controls.enable(self.delete_action,bool(self.selected_points) and not prompt_busy or not busy and bool(self.selected_ids or self.draft.get('base_id')))
        loading=self.progress_presentation.loading_active
        controls.enable(self.cancel_button,self.progress.model.state.can_cancel and (physical_busy or bool(loading and self.loading_task and not self.loading_task.cancel_event.is_set())))
        self.cancel_button.setText(ui_text('control_state.update_controls.011') if self.task_kind=='preparation' else ui_text('control_state.update_controls.012'))
        if not busy:
            names={'queued':ui_text('control_state.update_controls.013'),'preparing':ui_text('control_state.update_controls.014'),'paused':ui_text('control_state.update_controls.015'),'failed':ui_text('control_state.update_controls.016'),'bands_required':ui_text('control_state.update_controls.017')}
            self.state_label.setText(ui_text('control_state.update_controls.021') if ready else names.get(state,ui_text('control_state.update_controls.025') if not has else ui_text('control_state.update_controls.013')))
        else:
            from ..task_status import task_name
            self.state_label.setText(task_name(self.task_kind or self.progress.model.state.kind))
        set_tone(self.state_label,'busy' if busy else ('error' if state=='failed' else 'warning' if state in ['paused','bands_required'] else 'ready' if ready else 'idle'))
        self.update_reshape_controls(controls)
        selected=next((row for row in self.label_presenter.rows if row.identifier==self.selected_id),None) if len(self.selected_ids)==1 else None
        self.category_buttons.sync(self.project['classes'],selected.class_id if selected else None,bool(selected) and not busy)
        self.sync_manual_polygon()
        if self.draft.get('manual_vertices'):
            controls.enable(self.undo_prompt_action,not busy);controls.enable(self.redo_prompt_action,not busy and bool(self.prompt_redo))
        from ..model_catalog import model_title
        config=self.project['model'];self.model_button.setText(model_title(config))
        actual=self.runtime_status['device'] if self.runtime_status and self.runtime_status['signature']==digest(config) else None
        device=('GPU' if actual=='cuda' else ui_text('control_state.update_controls.023') if config['device']=='cuda' else 'CPU') if actual else (ui_text('control_state.update_controls.018') if config['device']=='cuda' else 'CPU')
        if self.task_kind in ('model','model_warmup'):model_state=ui_text('control_state.model_loading')
        elif self.task_kind=='preparation' and not actual:model_state=ui_text('control_state.model_preparing')
        else:model_state='' if actual else ui_text('control_state.update_controls.024')
        status_text=ui_text('model.device_label')+device+model_state
        runtime_hint=ui_text('control_state.update_controls.002')
        from ..native_runtime import lightweight
        import sys
        if lightweight() or getattr(sys,'frozen',False):
            from ..resource_state import snapshot
            if not snapshot(config)['ready']:
                status_text=ui_text('model.device_label')+device+ui_text('resources.missing_status')
                runtime_hint=ui_text('resources.missing_hint')
        self.model_runtime.setText(status_text)
        self.model_runtime.setToolTip(self.model_runtime.text()+'\n'+runtime_hint)
        controls.enable(self.vector_export_button,not busy and any(l['status']=='confirmed' for l in self.current_labels()))
        self.update_draft_info()
        self.sync_smoothing_controls()
        controls.apply()
        self.sync_overlay_visibility_button()
        self.progress_presentation.sync(self.task is not None)
        self.background_activity.refresh()

    def record_runtime(self,result):
        if result.get('device'):self.runtime_status={'signature':digest(self.project['model']),'device':result['device'],'execution':result.get('execution')}

