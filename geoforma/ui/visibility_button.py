"""A two-state status button, independent of toolbar selection highlighting."""
from PySide6.QtCore import QSize,Qt
from PySide6.QtWidgets import QToolButton
from ..tool_icons import icon


class VisibilityButton(QToolButton):
    def __init__(self,action,parent=None):
        super().__init__(parent);self.setFixedSize(30,30);self.setIconSize(QSize(18,18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._icons={True:icon('raw','#087F88'),False:icon('raw_hidden','#607A93')}
        self.setStyleSheet('''
QToolButton{padding:4px;border:1px solid;border-radius:5px;}
QToolButton[visibilityState="visible"]{background:#eaf6f2;border-color:#9acfc3;color:#087f88;}
QToolButton[visibilityState="hidden"]{background:#edf2f8;border-color:#b8c8d9;color:#607a93;}
QToolButton[visibilityState="visible"]:hover{background:#daefe7;border-color:#61b0a0;}
QToolButton[visibilityState="hidden"]:hover{background:#e1e9f4;border-color:#8da7c3;}
QToolButton[visibilityState="visible"]:pressed{background:#cde7df;border-color:#429785;}
QToolButton[visibilityState="hidden"]:pressed{background:#cfdce9;border-color:#7896b6;}
QToolButton:disabled{background:#f3f6f7;border-color:#dce5e9;color:#8799a3;}
''')
        self.setDefaultAction(action);action.changed.connect(self.sync_state);self.sync_state()

    def sync_state(self):
        action=self.defaultAction();visible=action.isChecked();state='visible' if visible else 'hidden'
        # QAction retains the visibility flag; this control presents status,
        # rather than inheriting the generic checked/unchecked toolbar appearance.
        if self.isCheckable():self.setCheckable(False)
        if self.property('visibilityState')!=state:
            self.setProperty('visibilityState',state);self.style().unpolish(self);self.style().polish(self);self.update()
        selected=self._icons[visible]
        if self.icon().cacheKey()!=selected.cacheKey():self.setIcon(selected)
        self.setProperty('feedback','normal' if visible else 'navigation')
        text='标签已显示，点击隐藏' if visible else '标签已隐藏，点击显示'
        if self.toolTip()!=text:self.setToolTip(text)
        name='标签显示' if visible else '标签隐藏'
        if self.accessibleName()!=name:self.setAccessibleName(name)
