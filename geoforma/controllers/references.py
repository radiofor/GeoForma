"""Reference import and toolbar selection never mutate model inputs or overlays."""
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from ..reference_images import (display_descriptor,reference_recipe,read_display,
    reference_group_name,suggested_reference_name,reference_origin)
from ..reference_catalog import ReferenceLookup,reference_key,reference_stem,merge_references,equivalent_reference
from ..raster import inspect_source
from ..operation_state import can_start_operation,interaction_locked
from ..ui.modal import dialog_result


class ReferenceWorkflow:
    def manage_references(self):
        if not can_start_operation(self):return
        from ..ui.reference_manager import ReferenceManagerDialog
        dialog=ReferenceManagerDialog(self.project.get('references',[]),self)
        accepted,result=dialog_result(dialog,lambda current:(current.references,current.replacement_for))
        if not accepted or result[0]==self.project.get('references',[]):return
        self.replace_references(*result)
        self.mark_dirty();self.update_controls();self.autosave()

    def import_references_dialog(self):
        if not can_start_operation(self) or self.reshape_session is not None:return
        paths,_=QFileDialog.getOpenFileNames(self,'导入参考影像',str(self.settings.value('last_reference_directory','') or ''),'TIF 影像或 VRT (*.tif *.tiff *.vrt);;VRT 批量导入 (*.vrt);;TIF 影像 (*.tif *.tiff)')
        if not paths:return
        from ..dialogs import ReferenceNameDialog
        dialog=ReferenceNameDialog(suggested_reference_name(paths),self)
        accepted,group=dialog_result(dialog,lambda current:current.value())
        if accepted:
            self.settings.setValue('last_reference_directory',str(Path(paths[0]).parent));self.import_reference_paths(paths,group)

    def import_reference_paths(self,paths,group):
        if not can_start_operation(self) or self.reshape_session is not None:return
        try:group=reference_group_name(group)
        except ValueError as error:self.statusBar().showMessage(str(error),5000);return
        if not self.project['images']:
            self.statusBar().showMessage('请先导入主影像，再添加参考',8000);return
        current=dict(self.image) if self.image else None
        stems={reference_stem(image['path']) for image in self.project['images']}
        def work(task):
            from ..image_list import plan_import
            task.signals.progress.emit(0,0,'读取文件引用')
            plan=plan_import(paths,check=task.check)
            references=[];errors=plan.errors;frames=[];seen=set();unmatched=0
            for i,(path,metadata) in enumerate(plan.entries):
                task.check()
                if reference_stem(path) not in stems:
                    unmatched+=1
                    task.signals.progress.emit(i+1,len(plan.entries),'未匹配 · '+Path(path).name)
                    continue
                try:
                    ref=inspect_source(path);key=reference_stem(ref['path'])
                    if key in seen:raise ValueError('同一参考类型存在多个同名影像，请分开导入。')
                    ref['display_recipe']=reference_recipe(ref);ref['group']=group
                    ref['reference_origin']=reference_origin(path,metadata)
                    if metadata:ref['import_list']=metadata
                    if current and reference_stem(current['path'])==key:
                        descriptor=display_descriptor(current,ref);window=[0,0,current['width'],current['height']]
                        frames.append((descriptor,window,read_display(descriptor,window,max_size=1400)))
                    references.append(ref);seen.add(key)
                except Exception as error:errors.append(f'{path}: {error}')
                task.signals.progress.emit(i+1,len(plan.entries),Path(path).name)
            task.check();return references,errors,frames,plan,unmatched
        def done(result):
            references,errors,frames,plan,unmatched=result;catalog=self.project.setdefault('references',[])
            if errors and not references:self.task_outcome='failed'
            for descriptor,window,value in frames:self.raster_renderer.prime(descriptor,window,1400,value)
            self.replace_references(merge_references(catalog,references))
            if references:self.mark_dirty()
            record=f'{group} 参考：导入 {len(references)} 幅，未匹配跳过 {unmatched} 幅，重复 {plan.duplicates} 项，失败 {len(errors)} 项。'
            skipped=unmatched+plan.duplicates
            summary=f'{group} · 成功 {len(references)} 幅'+(f' · 跳过 {skipped} 项' if skipped else '')+(f' · 失败 {len(errors)} 项' if errors else '')
            self.log_message(record);self.statusBar().showMessage(summary,8000)
            if errors:self.show_import_report(summary,errors)
        self.run(f'导入参考：{group}',work,done,kind='reference_import')

    def current_references(self):
        if not hasattr(self,'reference_lookup'):self.reference_lookup=ReferenceLookup()
        return self.reference_lookup.for_image(self.project.get('references',[]),self.image)

    def replace_references(self,records,replacement=None):
        old=self.display_reference;visible=getattr(self,'visible_reference',None)
        before=display_descriptor(self.image,old) if self.image else None
        self.project['references']=records;choices=self.current_references()
        def resolve(record):
            if record is None:return None
            mapped=replacement(record) if replacement else next((value for value in choices if reference_key(value)==reference_key(record)),None)
            return equivalent_reference(mapped,choices) if mapped is not None else None
        self.display_reference=resolve(old);self.visible_reference=resolve(visible)
        after=self.display_image();self.sync_reference_buttons()
        if before is not None and before['fingerprint']!=after['fingerprint']:self.start_reference_transition()

    def sync_reference_buttons(self):
        context=(self.project_epoch,self.image['id'] if self.image else None)
        if context!=getattr(self,'reference_context',None):
            self.reference_context=context;self.display_reference=None;self.visible_reference=None;self.reference_transition_pending=False
        refs=self.current_references()
        self.display_reference=equivalent_reference(self.display_reference,refs)
        enabled=bool(self.image) and not interaction_locked(self)
        self.main_image_button.setEnabled(enabled);self.main_image_button.setChecked(self.display_reference is None)
        self.settings_button.setEnabled(not self.closing)
        self.reference_manage_action.setEnabled(can_start_operation(self) and bool(self.project.get('references')))
        self.reference_switch_holder.set_references(refs,self.display_reference,enabled)
        self.reference_buttons=self.reference_switch_holder.buttons

    def reorder_reference_buttons(self,order):
        if interaction_locked(self) or not self.image:return
        visible=[record['group'].casefold() for record in self.current_references()]
        if len(order)!=len(visible) or set(order)!=set(visible):return
        from ..reference_catalog import reorder_reference_groups
        records=self.project.get('references',[]);updated=reorder_reference_groups(records,order)
        if updated is records:return
        self.project['references']=updated;self.sync_reference_buttons();self.mark_dirty()

    def switch_reference(self,reference):
        if interaction_locked(self):return
        current=equivalent_reference(reference,self.current_references())
        if reference is not None and current is None:return
        self.main_image_button.setChecked(current is None);self.reference_switch_holder.set_current(current)
        if current is self.display_reference:return
        self.display_reference=current;self.start_reference_transition()

    def start_reference_transition(self):
        self.reference_transition_pending=True;self.render_generation+=1;self.raster_renderer.reset(self.render_generation)
        self.render_timer.stop();self.request_render(True)

    def display_image(self):return display_descriptor(self.image,self.display_reference)

    def reference_render_failed(self,message):
        if not self.reference_transition_pending:return
        self.display_reference=getattr(self,'visible_reference',None);self.reference_transition_pending=False
        from ..error_messages import user_message
        self.sync_reference_buttons();self.statusBar().showMessage('参考读取失败 · '+user_message(message),8000)
