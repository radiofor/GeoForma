"""Shared first-click selection for editable text and numeric fields."""
from PySide6.QtCore import QEvent,QObject,Qt
from PySide6.QtWidgets import QAbstractSpinBox,QLineEdit,QPlainTextEdit,QTextEdit,QWidget


class InputSelection(QObject):
    def focus_in(self,field,event):
        field.setProperty('_firstClickSelectAll',True)
        if event.reason() in (Qt.FocusReason.MouseFocusReason,Qt.FocusReason.TabFocusReason,Qt.FocusReason.BacktabFocusReason):
            field.selectAll()

    def editable(self,obj):
        if isinstance(obj,(QLineEdit,QPlainTextEdit,QTextEdit)):
            return obj if obj.isEnabled() and not obj.isReadOnly() else None
        if isinstance(obj,QWidget):
            parent=obj.parentWidget()
            if isinstance(parent,(QPlainTextEdit,QTextEdit)) and parent.viewport() is obj:
                return parent if parent.isEnabled() and not parent.isReadOnly() else None
        return None

    def eventFilter(self,obj,event):
        kind=event.type()
        if kind not in (QEvent.Type.FocusIn,QEvent.Type.FocusOut,QEvent.Type.KeyPress,QEvent.Type.MouseButtonPress):return False
        if isinstance(obj,QAbstractSpinBox) and kind in (QEvent.Type.FocusIn,QEvent.Type.FocusOut):
            field=obj.lineEdit()
            if field is not None and obj.isEnabled() and not obj.isReadOnly():
                if kind==QEvent.Type.FocusIn:self.focus_in(field,event)
                else:field.setProperty('_firstClickSelectAll',False)
            return False
        field=self.editable(obj)
        if field is None:return False
        if kind==QEvent.Type.FocusIn and obj is field:
            self.focus_in(field,event)
        elif kind==QEvent.Type.FocusOut and obj is field:
            field.setProperty('_firstClickSelectAll',False)
        elif kind==QEvent.Type.KeyPress:
            field.setProperty('_firstClickSelectAll',False)
        elif kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            if not event.modifiers() and (not field.hasFocus() or field.property('_firstClickSelectAll')):
                field.setFocus(Qt.FocusReason.MouseFocusReason);field.selectAll()
                field.setProperty('_firstClickSelectAll',False);event.accept();return True
            field.setProperty('_firstClickSelectAll',False)
        return False


def install_input_selection(app):
    if hasattr(app,'_geoforma_input_selection'):return
    selection=InputSelection(app);app._geoforma_input_selection=selection;app.installEventFilter(selection)
