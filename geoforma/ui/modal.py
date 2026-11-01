"""Release transient dialogs, deferring only while their task callbacks still use them."""


def dialog_result(dialog,value=None,owner=None):
    try:
        accepted=bool(dialog.exec())
        return accepted,value(dialog) if accepted and value is not None else None
    finally:
        task=getattr(owner,'task',None) if owner is not None else None
        if task is not None:task.signals.finished.connect(dialog.deleteLater)
        else:dialog.deleteLater()
