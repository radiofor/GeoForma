"""ImageWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy
from pathlib import Path
from PySide6.QtCore import Qt, QRectF,QSignalBlocker,QTimer
from PySide6.QtWidgets import QFileDialog, QInputDialog
from ..raster import inspect_source, make_recipe
from ..dialogs import BandsDialog
from ..operation_state import can_start_operation
from ..ui.modal import dialog_result


class ImageWorkflow:
    def import_dialog(self):
        if not can_start_operation(self):return
        directory=str(self.settings.value('last_import_directory','') or '')
        if not directory or not Path(directory).is_dir():directory=''
        self.import_button.setDown(True);self.import_button.repaint()
        try:files,_=QFileDialog.getOpenFileNames(self,ui_text('images.import_dialog.008'),directory,ui_text('images.import_dialog.009'))
        finally:self.import_button.setDown(False)
        if files:
            self.settings.setValue('last_import_directory',str(Path(files[0]).resolve().parent));self.settings.sync()
            self.import_paths(files)

    def import_paths(self,paths):
        if not paths or not can_start_operation(self):return
        paths=tuple(paths);existing=tuple(v['path'] for v in self.project['images'])
        def work(task):
            from ..image_list import plan_import
            task.signals.progress.emit(0,0,'读取文件引用')
            plan=plan_import(paths,existing,task.check);images=[]
            for i,(path,metadata) in enumerate(plan.entries):
                task.check()
                try:
                    image=inspect_source(path)
                    image['review_complete']=False
                    if metadata:
                        image['import_list']=metadata
                        if metadata.get('name'):image['name']=metadata['name']
                    if image['suggested_bands']:
                        image['model_recipe']=make_recipe(image,image['suggested_bands']);image['display_recipe']=copy.deepcopy(image['model_recipe'])
                    images.append(image)
                except Exception as e:plan.errors.append(f'{path}: {e}')
                task.signals.progress.emit(i+1,len(plan.entries),Path(path).name)
            task.check();return images,plan
        def done(result):
            images,plan=result
            if plan.errors and not images:self.task_outcome='failed'
            if images:
                self.project['images'].extend(images);self.refresh_images();self.mark_dirty()
                row=len(self.project['images'])-len(images)
                with QSignalBlocker(self.images):self.images.setCurrentRow(row)
                self._activate_image(row)
                if not self.auto_prepare:self.queue_preparation()
            summary=plan.summary(len(images));self.log_message(summary);self.statusBar().showMessage(summary,8000)
            if plan.errors:self.show_import_report(summary,plan.errors)
        self.run(ui_text('images.import_paths.001'),work,done,kind='import')

    def show_import_report(self,summary,errors):
        for error in errors[:500]:self.log_message(error)
        if len(errors)>500:self.log_message(f'其余 {len(errors)-500} 项未列出。')
        self.statusBar().report_error(summary,source='import_report')

    def refresh_images(self):
        from ..ui.raster_presenter import build_raster_rows
        current=self.image['id'] if self.image else None;rows=build_raster_rows(self.project['images'])
        self.raster_presenter.sync(rows,current,animate=self.task_kind=='import')

    def toggle_image_review(self,identifier):
        from ..operation_state import interaction_locked,can_browse
        if interaction_locked(self) or not can_browse(self):return
        index=next((i for i,image in enumerate(self.project['images']) if image['id']==identifier),None)
        if index is None:return
        image=self.project['images'][index];complete=not image.get('review_complete',False)
        image['review_complete']=complete;self.mark_dirty();self.refresh_images()
        if complete and index+1<len(self.project['images']):self.images.setCurrentRow(index+1)

    def complete_current_image(self):
        if self.image and not self.image.get('review_complete',False):self.toggle_image_review(self.image['id'])

    def change_image(self,row):
        from ..operation_state import interaction_locked,can_browse
        if interaction_locked(self) or not can_browse(self):
            current=next((i for i,image in enumerate(self.project['images']) if image is self.image),-1)
            with QSignalBlocker(self.images):self.images.setCurrentRow(current)
            return
        if row<0 or row>=len(self.project['images']):return
        target=self.project['images'][row]
        if target is self.image:
            self.cancel_image_switch();return
        # Keep the current image and its selection coherent while a new
        # overview is read. Cached overviews switch immediately.
        if self.image and self.view.layers.base_item is not None and target.get('display_recipe'):
            window=[0,0,target['width'],target['height']]
            if not self.raster_renderer.has_cached(target,window,1400):
                self.prepare_image_switch(row,target,window);return
        self.cancel_image_switch()
        self._activate_image(row)

    def cancel_image_switch(self):
        self._image_switch_serial=getattr(self,'_image_switch_serial',0)+1
        task=getattr(self,'_image_switch_task',None)
        if task is not None:task.cancel()

    def prepare_image_switch(self,row,target,window):
        from ..tasks import Task
        from ..rendering.raster_queue import display_snapshot
        self.cancel_image_switch();serial=self._image_switch_serial
        current=self.image;epoch=self.project_epoch;revision=self.state.interaction_revision;reshape=self.reshape_session
        selection=(frozenset(self.selected_ids),frozenset(self.selected_points),self.annotation_mode())
        navigation=self.view.capture_navigation()
        current_row=next((i for i,image in enumerate(self.project['images']) if image is current),-1)
        with QSignalBlocker(self.images):self.images.setCurrentRow(current_row)
        snapshot=display_snapshot(target)
        def work(task):
            task.check();value=self.raster_renderer.reader(snapshot,window,snapshot['display_recipe'],1400);task.check();return value
        task=Task(work);self._image_switch_task=task
        def valid():
            from ..operation_state import interaction_locked,can_browse
            return (not self.closing and serial==self._image_switch_serial and epoch==self.project_epoch and
                    revision==self.state.interaction_revision and self.image is current and row<len(self.project['images']) and
                    self.project['images'][row] is target and not interaction_locked(self) and
                    selection==(frozenset(self.selected_ids),frozenset(self.selected_points),self.annotation_mode()) and
                    navigation==self.view.capture_navigation() and self.reshape_session is reshape and can_browse(self))
        def retry_changed_target():
            if display_snapshot(target)==snapshot:return False
            if target.get('display_recipe'):
                self.prepare_image_switch(row,target,[0,0,target['width'],target['height']])
            else:
                self.cancel_image_switch()
                with QSignalBlocker(self.images):self.images.setCurrentRow(row)
                self._activate_image(row)
            return True
        def ready(value):
            if not valid():return
            if retry_changed_target():return
            self.raster_renderer.prime(snapshot,window,1400,value)
            with QSignalBlocker(self.images):self.images.setCurrentRow(row)
            self._activate_image(row)
        def failed(message):
            if valid() and not task.cancel_event.is_set():
                if retry_changed_target():return
                from ..error_messages import user_message
                self.log_message(message);self.statusBar().report_error('读取影像失败：'+user_message(message),source='image_read')
        def finished():
            if getattr(self,'_image_switch_task',None) is task:self._image_switch_task=None
            if self.closing:QTimer.singleShot(0,self.close)
        task.signals.result.connect(ready);task.signals.error.connect(failed);task.signals.finished.connect(finished)
        self.render_pool.start(task,-1)

    def _activate_image(self,row):
        if row<0 or row>=len(self.project['images']):return
        if self.image is self.project['images'][row]:return
        self.interrupt_reshape()
        target=self.project['images'][row]
        window=[0,0,target['width'],target['height']]
        previous_rows=self.label_presenter.rows
        self.label_presenter.transition.capture()
        transition=bool(self.image and target.get('display_recipe') and self.raster_renderer.has_cached(target,window,1400))
        if transition:self.view.frame_transition.capture()
        else:self.view.frame_transition.cancel()
        self.invalidate_preview()
        self.auto_apply_timer.stop()
        if self.label_index_task:self.label_index_task.cancel()
        self.store_image_session()
        self.last_error=''
        self.image=self.project['images'][row];session=self.load_image_session()
        if 'class_id' in self.draft:
            self.classes.blockSignals(True);self.classes.setCurrentIndex(self.classes.findData(self.draft['class_id']));self.classes.blockSignals(False)
        self.selected_points.clear();self.render_generation+=1;self.raster_renderer.reset(self.render_generation);self.view.switch_image(self.image['width'],self.image['height'])
        if session.get('navigation'):self.view.restore_navigation(session['navigation'])
        elif session.get('view'):self.view.fitInView(QRectF(*session['view']),Qt.AspectRatioMode.KeepAspectRatio)
        # Start I/O before building the table and annotation layer, so those
        # GUI updates overlap the overview read. Reset the reference context
        # first: references always belong to the newly activated image.
        self.sync_reference_buttons()
        self.transition_detail=(self.render_generation,self.raster_renderer.revision) if transition else None
        self.request_render(True)
        self.refresh_info();self.update_draft_info();self.refresh_labels();self.mark_dirty()
        self.label_presenter.transition.reveal(previous_rows!=self.label_presenter.rows)
        if transition and self.view.layers.base_item is not None:self.view.frame_transition.reveal()
        else:self.view.frame_transition.cancel()
        if self.auto_prepare:self.queue_preparation()

    def store_image_session(self):
        if not self.image:return
        draft={k:copy.deepcopy(v) for k,v in self.draft.items() if k not in ('logits','choices')}
        self.image['working_draft']=draft
        mode=self.annotation_mode()
        saved={'draft':draft,'class_id':self.classes.currentData(),'view':self.view.visible_window(),'navigation':self.view.capture_navigation(),'selected_ids':sorted(self.selected_ids),
               'undo':copy.deepcopy(self.prompt_undo),'redo':copy.deepcopy(self.prompt_redo)}
        self.image.setdefault('mode_sessions',{})[mode]=saved
        self.image_sessions[(self.image['id'],mode)]=saved

    def load_image_session(self):
        mode=self.annotation_mode();session=self.image_sessions.get((self.image['id'],mode),self.image.get('mode_sessions',{}).get(mode,{}))
        self.draft=copy.deepcopy(session.get('draft',{}));self.prompt_undo=copy.deepcopy(session.get('undo',[]));self.prompt_redo=copy.deepcopy(session.get('redo',[]))
        if not self.draft.get('base_id') and not self.draft.get('geometry') and not self.draft.get('points') and not self.draft.get('box') and not self.draft.get('manual_vertices') and not (self.prompt_undo or self.prompt_redo):self.draft={}
        live={l['id'] for l in self.current_labels()};selected=set(session.get('selected_ids',[]))&live
        self.selected_ids=selected;self.selected_id=next(iter(selected)) if len(selected)==1 else None
        if session.get('class_id'):
            blocked=self.classes.blockSignals(True);self.classes.setCurrentIndex(self.classes.findData(session['class_id']));self.classes.blockSignals(blocked)
        return session

    def refresh_info(self):
        if not self.image:self.image_info.clear();return
        im=self.image;crs=im.get('assigned_crs') or im['crs'] or ui_text('images.refresh_info.002');r=im.get('model_recipe');rgb='/'.join(map(str,r['bands'])) if r else ui_text('images.refresh_info.003')
        directory=str(Path(im['path']).resolve().parent)
        self.image_info.setText(ui_text('images.refresh_info.004').format(p0=im['width'],p1=im['height'],p2=im['bands'],p3=crs,p4=rgb)+'\n文件目录：'+directory)
        self.image_info.setToolTip(ui_text('images.refresh_info.013').format(p0=crs,p2=im['dtypes'][0],p3=im['source_files'],p4=im['path']))

    def configure_bands(self):
        self.invalidate_preview()
        if not self.image or self.task:return
        accepted,value=dialog_result(BandsDialog(self.image,self),lambda dialog:dialog.values())
        if not accepted:return
        bands,ranges,stretch,target=value;im=self.image
        if stretch==1 and any(hi<=lo for lo,hi in ranges):self.statusBar().report_error(ui_text('images.configure_bands.015'));return
        def work(task):
            if stretch==0:return make_recipe(im,bands)
            from ..raster import mark_recipe_policy
            return mark_recipe_policy(im,{'bands':bands,'ranges':ranges,'format':'RGB uint8','nodata_fill':0})
        def done(recipe):
            if target in [0,1]:im['display_recipe']=copy.deepcopy(recipe)
            if target in [0,2]:
                im['model_recipe']=copy.deepcopy(recipe);im['ready']=False
                self.invalidate_model_drafts({im['id']})
            self.render_generation+=1;self.raster_renderer.reset(self.render_generation);self.request_render(True);self.refresh_info();self.refresh_images();self.redraw();self.mark_dirty()
            if target in [0,2]:self.queue_preparation()
        self.run(ui_text('images.configure_bands.005'),work,done,kind='bands')

    def assign_crs(self):
        if not self.image or self.task:return
        value,ok=QInputDialog.getText(self,ui_text('images.assign_crs.006'),ui_text('images.assign_crs.007'),text=self.image.get('assigned_crs') or self.image['crs'])
        if ok:
            try:
                from rasterio.crs import CRS
                self.image['assigned_crs']=CRS.from_user_input(value).to_string();self.refresh_info();self.mark_dirty()
            except Exception as e:self.error(str(e))

