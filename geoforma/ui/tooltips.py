"""Disable hover-help popups throughout the application."""
from PySide6.QtCore import QObject,QEvent


class ToolTipBlocker(QObject):

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.ToolTip:
            event.accept();return True
        return False


def install_tooltips(app):
    if hasattr(app,'_geoforma_tooltips'):return
    policy=ToolTipBlocker(app);app._geoforma_tooltips=policy;app.installEventFilter(policy)
