"""Apply only final control states, avoiding enable/disable/repaint oscillation."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class ControlUpdate:
    def __init__(self):self.enabled={};self.visibility={};self.texts={}

    def enable(self,widget,value):self.enabled[widget]=bool(value)
    def show(self,widget,value):self.visibility[widget]=bool(value)
    def text(self,widget,value):self.texts[widget]=value
    def is_enabled(self,widget):return self.enabled.get(widget,widget.isEnabled())

    def apply(self):
        for widget,value in self.enabled.items():
            current=not widget.testAttribute(Qt.WidgetAttribute.WA_ForceDisabled) if isinstance(widget,QWidget) else widget.isEnabled()
            if current!=value:widget.setEnabled(value)
        for widget,value in self.visibility.items():
            if widget.isHidden()==value:widget.setVisible(value)
        for widget,value in self.texts.items():
            if widget.text()!=value:widget.setText(value)
