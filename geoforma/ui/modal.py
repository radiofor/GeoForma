"""Release transient dialogs, deferring only while their task callbacks still use them."""


def dialog_buttons(parent):
    from PySide6.QtWidgets import QDialogButtonBox
    from .text import ui_text
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ui_text('dialogs.dialog_buttons.001'))
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ui_text('control_state.update_controls.012'))
    buttons.accepted.connect(parent.accept);buttons.rejected.connect(parent.reject)
    return buttons


def dialog_result(dialog,value=None,owner=None):
    try:
        accepted=bool(dialog.exec())
        return accepted,value(dialog) if accepted and value is not None else None
    finally:
        task=getattr(owner,'task',None) if owner is not None else None
        if task is not None:task.signals.finished.connect(dialog.deleteLater)
        else:dialog.deleteLater()
