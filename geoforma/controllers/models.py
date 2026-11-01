"""ModelWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy
from pathlib import Path
from ..dialogs import ModelDialog
from ..operation_state import can_start_operation
from ..ui.modal import dialog_result


class ModelWorkflow:
    def remember_current_model(self):
        from ..model_preferences import remember_model
        if not remember_model(self.settings,self.project['model']):self.log_message(ui_text('models.preference_error'))

    def configure_model(self):
        self.invalidate_preview()
        if not can_start_operation(self):return
        accepted,value=dialog_result(ModelDialog(self.project['model'],self),lambda dialog:dialog.value())
        if accepted:
            self.resource_reminded=False
            if value!=self.project['model']:
                self.project['model']=value
                for im in self.project['images']:im['ready']=False
                self.invalidate_model_drafts()
                self.refresh_images();self.redraw();self.update_draft_info();self.update_controls();self.mark_dirty()
            self.remember_current_model()
            if not self.project['images'] and self.image is None:return
            if value!=getattr(self,'prepared_model_config',None) or not Path(value['checkpoint']).is_file():
                def done(result):
                    self.project['model']['checkpoint']=result['checkpoint'];self.prepared_model_config=copy.deepcopy(self.project['model']);self.record_runtime(result);self.mark_dirty()
                    self.remember_current_model()
                    self.log_message(ui_text('models.done.002')+result['device']+' · '+result['checkpoint'])
                    self.queue_preparation()
                self.run(ui_text('models.configure_model.001'),lambda t:self.service.prepare_model(copy.deepcopy(value),t),done,kind='model')

