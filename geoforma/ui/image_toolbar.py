"""Keep image tools directly accessible when side panels narrow the canvas."""
from PySide6.QtCore import Qt,QEvent,QTimer
from PySide6.QtWidgets import QToolBar, QToolButton,QWidget,QBoxLayout


class ImageToolbarRow(QWidget):
    """Keep source controls visible and wrap the two groups on narrow canvases."""
    def __init__(self,tools,sources,reference_strip,parent=None):
        super().__init__(parent);self.reference_strip=reference_strip;self.sources=sources;self.tools=tools;self.stacked=None;self.pending=False
        self.row=QBoxLayout(QBoxLayout.Direction.LeftToRight,self);self.row.setContentsMargins(0,0,0,0);self.row.setSpacing(0)
        self.row.addWidget(tools,1);self.row.addWidget(sources,0,Qt.AlignmentFlag.AlignRight)
        tools.installEventFilter(self);sources.installEventFilter(self)

    def resizeEvent(self,event):
        super().resizeEvent(event);stacked=self.width()<760
        if stacked!=self.stacked:
            self.stacked=stacked
            self.row.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        self.schedule_fit()

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.Resize,QEvent.Type.LayoutRequest):self.schedule_fit()
        return super().eventFilter(obj,event)

    def schedule_fit(self):
        if not self.pending:self.pending=True;QTimer.singleShot(0,self.fit_references)

    def fit_references(self):
        self.pending=False;layout=self.sources.layout();margins=layout.contentsMargins()
        widgets=[layout.itemAt(i).widget() for i in range(layout.count())]
        # The reference strip is the only expandable source control.
        fixed=[widget for widget in widgets if widget is not None and widget is not self.reference_strip]
        base=margins.left()+margins.right()+sum(max(widget.minimumWidth(),widget.sizeHint().width()) for widget in fixed)+layout.spacing()*len(fixed)
        tools_width=0 if self.stacked else self.tools.sizeHint().width()
        self.reference_strip.set_width_limit(max(0,self.width()-base-tools_width))


class ImageToolBar(QToolBar):
    def resizeEvent(self,event):
        super().resizeEvent(event)
        compact=self.width()<800
        for action in self.actions():
            button=self.widgetForAction(action)
            if isinstance(button,QToolButton):
                style=Qt.ToolButtonStyle.ToolButtonIconOnly if compact or action.property('iconOnly') else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                if button.toolButtonStyle()!=style:button.setToolButtonStyle(style)
