"""Workbench adapter for the shared progress lifecycle and renderer."""
from PySide6.QtCore import QTimer
from ..task_status import task_name,progress_name,task_detail,task_subject,visible_detail,task_message
from ..theme import set_tone
from .text import ui_text


class TaskProgressPresentation:
    """Keep the last result visible until a new foreground task replaces it."""
    def __init__(self,window):
        self.window=window;self.total=0;self.loading_title=None;self.loading_stage=''
        self.clear_timer=QTimer(window);self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self.clear_terminal)

    @property
    def kind(self):return self.window.progress.model.state.kind

    @property
    def result(self):
        state=self.window.progress.model.state
        return (state.title,state.phase) if state.phase in ('complete','cancelled','failed') else None

    @property
    def loading_active(self):return self.loading_title is not None

    def begin(self,kind=None,title=None):
        self.clear_timer.stop()
        self.total=0;kind=kind or self.window.task_kind;self.loading_title=None;self.loading_stage=''
        self.window.progress_count_text=''
        for control in (self.window.state_label,self.window.progress_percent,self.window.progress,self.window.progress_action):control.show()
        self.window.progress_percent.setText('--%')
        self.window.statusBar().clearMessage()
        self.window.state_label.setProperty('taskKind',kind)
        self.token=self.window.progress.model.begin(title or getattr(self.window,'task_title','') or task_name(kind),
                                                   kind,cancellable=kind!='runtime_remove')

    def report(self,current,total,stage):
        if self.window.progress.model.report(current,total,stage,token=getattr(self,'token',None)):self.total=total

    def request_cancel(self,stage):
        w=self.window
        if not w.progress.model.request_cancel(stage,token=getattr(self,'token',None)):return False
        if self.loading_active:self.loading_stage=stage;w.task_text.setText(task_message(self.loading_title,stage,self.kind,count=w.progress_count_text))
        return True

    def begin_loading(self,kind,title):
        self.begin(kind,title);self.loading_title=title
        self.update_loading(0,0,'读取项目文件')

    def update_loading(self,current,total,text):
        if not self.loading_active:return
        if not self.window.progress.model.report(current,total,text,token=self.token):return
        w=self.window;self.loading_stage=text;self.total=total
        w.progress_count_text=f'轮廓 {current} / {total}' if total>0 else ''
        w.progress_percent.setText(f'{100*max(0,min(current,total))//total}%' if total>0 else '--%')
        w.task_text.setText(task_message(self.loading_title,text,self.kind,count=w.progress_count_text))
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
        if outcome=='complete':w.progress_percent.setText('100%')
        if outcome=='complete':
            if self.total>0:
                if loading:w.progress_count_text=f'轮廓 {self.total} / {self.total}'
                else:w.update_progress_count(self.total,self.total)
        if self.total<=0 and not getattr(w,'progress_image_order',None):w.progress_count_text=''
        text=self.outcome_label(outcome)
        w.progress_panel.setToolTip(title+' · '+text)
        if outcome!='failed' and not w.statusBar().currentMessage() and not (self.kind=='reshape' and outcome=='complete'):
            detail=task_subject(title,self.kind)
            operation={'preparation':'影像预处理','import':'影像导入','reference_import':'参考影像导入',
                       'model':'模型加载','model_warmup':'模型加载','export':'标签导出'}.get(self.kind,task_name(self.kind))
            result={'complete':'完成','cancelled':self.outcome_label(outcome),'failed':'失败'}[outcome]
            message=operation+result+(' · '+detail if detail else '')
            if self.kind=='preparation' and outcome=='complete':
                images=w.project.get('images',[])
                from ..workflow import all_fully_prepared
                if all_fully_prepared(images,w.project['model']):
                    message=f'全部影像预处理完成 · 共 {len(images)} 幅'
            w.statusBar().showMessage(message,5000)
        self.clear_timer.start(5000)

    def clear_terminal(self):
        """Clear a finished meter while keeping the progress panel in place."""
        w=self.window
        if w.task is not None or self.loading_active or w.progress.model.state.phase=='running':return
        self.clear_timer.stop()
        for control in (w.state_label,w.progress_percent,w.progress,w.progress_action):control.hide()
        w.progress_panel.setToolTip('')

    def restore_text(self):
        w=self.window
        if w.last_error:w.task_text.setText('')
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
            w.state_label.setText(progress_name(self.kind))
            set_tone(w.state_label,{'complete':'ready','cancelled':'warning','failed':'error'}[self.result[1]])
        elif w.progress.model.state.phase=='idle':self.restore_text()
