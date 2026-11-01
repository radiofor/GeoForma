"""Keep image tools directly accessible when side panels narrow the canvas."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar, QToolButton,QWidget,QBoxLayout


class ImageToolbarRow(QWidget):
    """Keep source controls visible and wrap the two groups on narrow canvases."""
    def __init__(self,tools,sources,reference_space,parent=None):
        super().__init__(parent);self.reference_space=reference_space;self.sources=sources;self.stacked=None
        self.row=QBoxLayout(QBoxLayout.Direction.LeftToRight,self);self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(0)
        self.row.addWidget(tools,1);self.row.addWidget(sources,0,Qt.AlignmentFlag.AlignRight)

    def resizeEvent(self,event):
        super().resizeEvent(event);stacked=self.width()<760
        if stacked!=self.stacked:
            self.stacked=stacked
            self.row.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        # Eye, main image, management, spacing: these stay outside the scroller.
        self.reference_space(max(0,min(320,self.width()-180-(0 if stacked else 400))))


class ImageToolBar(QToolBar):
    def resizeEvent(self,event):
        super().resizeEvent(event)
        compact=self.width()<800
        for action in self.actions():
            button=self.widgetForAction(action)
            if isinstance(button,QToolButton):
                style=Qt.ToolButtonStyle.ToolButtonIconOnly if compact or action.property('iconOnly') else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if button.toolButtonStyle()!=style:button.setToolButtonStyle(style)
