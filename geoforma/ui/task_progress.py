"""Workbench adapter for the shared progress lifecycle and renderer."""
from ..task_status import task_name,progress_name,task_detail,task_subject,visible_detail
from ..theme import set_tone
from .text import ui_text


class TaskProgressPresentation:
    """Keep the last result visible until a new foreground task replaces it."""
    def __init__(self,window):
        self.window=window;self.total=0;self.loading_title=None;self.loading_stage=''

    @property
    def kind(self):return self.window.progress.model.state.kind

    @property
    def result(self):
        state=self.window.progress.model.state
        return (state.title,state.phase) if state.phase in ('complete','cancelled','failed') else None

    @property
    def loading_active(self):return self.loading_title is not None

    def begin(self,kind=None,title=None):
        self.total=0;kind=kind or self.window.task_kind;self.loading_title=None;self.loading_stage=''
        self.window.progress_count.hide()
        for control in (self.window.progress,self.window.progress_action):control.show()
        # Reserve room for image and block counts only when that task needs it.
        # Width stays fixed throughout each task to avoid progress flicker.
        self.window.progress_count.setFixedWidth(160 if kind=='preparation' else 105)
        self.window.statusBar().clearMessage()
        self.window.state_label.setProperty('taskKind',kind)
        self.token=self.window.progress.model.begin(title or getattr(self.window,'task_title','') or task_name(kind),
                                                   kind,cancellable=kind!='runtime_remove')

    def report(self,current,total,stage):
        if self.window.progress.model.report(current,total,stage,token=getattr(self,'token',None)):self.total=total

    def request_cancel(self,stage):
        w=self.window
        if not w.progress.model.request_cancel(stage,token=getattr(self,'token',None)):return False
        if self.loading_active:self.loading_stage=stage;w.task_text.setText(visible_detail(self.loading_title,stage,self.kind))
        return True

    def begin_loading(self,kind,title):
        self.begin(kind,title);self.loading_title=title
        self.update_loading(0,0,'读取项目文件')

    def update_loading(self,current,total,text):
        if not self.loading_active:return
        if not self.window.progress.model.report(current,total,text,token=self.token):return
        w=self.window;self.loading_stage=text;self.total=total
        w.task_text.setText(visible_detail(self.loading_title,text,self.kind))
        w.progress_count.setText(f'轮廓 {current} / {total}' if total>0 else '')
        w.progress_count.setVisible(total>0)
        self.sync(False)

    def finish_loading(self,outcome):
        if not self.loading_active:return
        title=self.loading_title;self.loading_title=None;self.loading_stage=''
        self.finish(title,outcome,loading=True);self.restore_text()

    def outcome_label(self,outcome):
        if outcome=='cancelled' and self.kind=='resource_install':return ui_text('resources.cancelled')
        if outcome=='cancelled' and self.kind=='preparation':return '已暂停'
        return {'complete':'已完成','cancelled':'已取消','failed':'失败'}[outcome]

    def finish(self,title,outcome,loading=False):
        w=self.window
        if not w.progress.model.finish(outcome,token=self.token):return
        outcome=w.progress.model.state.phase
        if outcome=='complete':
            if self.total>0:
                if loading:w.progress_count.setText(f'轮廓 {self.total} / {self.total}')
                else:w.update_progress_count(self.total,self.total)
        if self.total<=0 and not getattr(w,'progress_image_order',None):w.progress_count.setText('');w.progress_count.hide()
        text=self.outcome_label(outcome)
        w.progress_result.setText(text)
        set_tone(w.progress_result,{'complete':'ready','cancelled':'warning','failed':'error'}[outcome])
        for widget in (w.progress_panel,w.progress_result):widget.setToolTip(title+' · '+text)

    def restore_text(self):
        w=self.window
        if w.last_error:w.task_text.setText(w.last_error)
        elif self.result:
            title,outcome=self.result
            if outcome=='complete' and self.kind in ('model','model_warmup'):
                w.task_text.setText(task_subject(title,self.kind))
            elif outcome=='complete' and self.kind=='resource_install' and title.startswith('配置 SAM'):
                w.task_text.setText(title.removeprefix('配置 '))
            else:
                stage=w.progress.model.state.stage if self.kind in ('import','reference_import') and outcome=='complete' else ''
                w.task_text.setText(visible_detail(title,stage,self.kind))
        else:
            image=w.image
            w.task_text.setText('当前影像 · '+(image.get('name') or image.get('path','')) if image else '导入影像以开始标注')

    def sync(self,busy):
        w=self.window;active=busy or self.loading_active
        w.progress_action.setCurrentIndex(0 if active else 1)
        if self.loading_active:
            w.progress_panel.setToolTip(task_detail(self.loading_title,self.loading_stage,self.kind))
            w.state_label.setText(task_name(self.kind));set_tone(w.state_label,'busy')
            return
        if busy:
            w.progress_panel.setToolTip(getattr(w,'task_title',''))
            w.state_label.setText(progress_name(w.task_kind,getattr(w,'task_stage','')));set_tone(w.state_label,'busy')
        elif self.result:
            w.state_label.setText(task_name(self.kind))
            set_tone(w.state_label,{'complete':'ready','cancelled':'warning','failed':'error'}[self.result[1]])
        elif w.progress.model.state.phase=='idle':self.restore_text()
