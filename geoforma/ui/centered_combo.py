"""Shared centered controls with a consistently spaced, anchored list popup."""
from PySide6.QtCore import Qt,QEvent,QSize,QPoint,QPropertyAnimation,QEasingCurve
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication,QComboBox,QStyle,QStyleOptionComboBox,QStylePainter,
    QStyledItemDelegate,QListView,QAbstractItemView,QProxyStyle,QStyleFactory,QFrame)


class ComboPopupStyle(QProxyStyle):
    def styleHint(self,hint,option=None,widget=None,returnData=None):
        # A list anchored to the field, instead of a menu centered on its item.
        if hint==QStyle.StyleHint.SH_ComboBox_Popup:return 0
        return super().styleHint(hint,option,widget,returnData)


class ComboItemDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        size=super().sizeHint(option,index)
        return QSize(size.width(),max(32,option.fontMetrics.height()+14))


class CenteredComboBox(QComboBox):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._popup_style=ComboPopupStyle(QStyleFactory.create('Fusion'));self._popup_style.setParent(self);self.setStyle(self._popup_style)
        view=QListView(self);view.setObjectName('comboList');view.setUniformItemSizes(True)
        view.setSpacing(2);view.setMouseTracking(True);view.setFrameShape(QFrame.Shape.NoFrame)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(view);self.setItemDelegate(ComboItemDelegate(view));self.setMaxVisibleItems(10)
        view.window().setFrameShape(QFrame.Shape.NoFrame)
        self.model().rowsInserted.connect(self._center_rows)
        self._reveal=None;self.expand_popup=False

    def event(self,event):
        if event.type()==QEvent.Type.FontChange:self.view().setFont(self.font())
        return super().event(event)

    def wheelEvent(self,event):
        # Scrolling over a field must not change its value, even with focus.
        # Ignoring the event lets an enclosing panel continue to scroll.
        event.ignore()

    def showPopup(self):
        if not self.isEnabled() or not self.count():return
        view=self.view();view.setFont(self.font())
        if self.expand_popup:view.setGridSize(QSize())
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if self.expand_popup else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setTextElideMode(Qt.TextElideMode.ElideNone if self.expand_popup else Qt.TextElideMode.ElideRight)
        popup=view.window();popup.setUpdatesEnabled(False)
        if self._reveal is not None:self._reveal.stop()
        effects=QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
        animate=QApplication.platformName()!='offscreen' and effects
        popup.setWindowOpacity(0. if animate else 1.)
        # Qt's menu-scroll effect captures and moves the old popup geometry.
        # Suppress it for this synchronous show; our fade keeps the frame fixed.
        if effects:QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo,False)
        try:
            super().showPopup()
            # Resolve all bounds before the first painted frame, including an
            # upward opening near a screen edge and narrow sidebar controls.
            # Leave room for the platform popup frame as well as its content.
            popup=view.window();screen=self.screen().availableGeometry().adjusted(4,4,-4,-4)
            below=self.mapToGlobal(QPoint(0,self.height()+4));above=self.mapToGlobal(QPoint(0,-4))
            content_width=view.sizeHintForColumn(self.modelColumn())+24 if self.expand_popup else self.width()
            width=min(max(self.width(),content_width),screen.width());height=popup.height()
            if self.expand_popup and content_width>width:height+=view.horizontalScrollBar().sizeHint().height()
            left=max(screen.left(),min(below.x(),screen.right()-width+1))
            lower=max(0,screen.bottom()-below.y()+1);upper=max(0,above.y()-screen.top())
            downward=height<=lower or lower>=upper
            height=max(1,min(height,screen.height(),lower if downward else upper))
            top=max(screen.top(),min(below.y() if downward else above.y()-height,screen.bottom()-height+1))
            popup.setGeometry(left,top,width,height)
            gutter=view.verticalScrollBar().width() if not self.expand_popup and view.verticalScrollBar().isVisible() else 0
            view.setViewportMargins(0,0,gutter,0) if self.layoutDirection()==Qt.LayoutDirection.RightToLeft else view.setViewportMargins(gutter,0,0,0)
            if self.expand_popup:
                # QListView otherwise shrinks every row to its viewport, which
                # clips long names and leaves no horizontal scroll range.
                view.setGridSize(QSize(max(view.viewport().width(),content_width-24),view.sizeHintForRow(0)+view.spacing()*2))
                view.doItemsLayout()
            view.scrollTo(self.model().index(self.currentIndex(),self.modelColumn(),self.rootModelIndex()),QAbstractItemView.ScrollHint.EnsureVisible)
            if self.expand_popup:view.horizontalScrollBar().setValue(0)
        finally:
            if effects:QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo,True)
            popup.setUpdatesEnabled(True)
        if animate:
            if self._reveal is None:
                self._reveal=QPropertyAnimation(popup,b'windowOpacity',self);self._reveal.setDuration(100);self._reveal.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._reveal.setStartValue(0.);self._reveal.setEndValue(1.);self._reveal.start()

    def hidePopup(self):
        if self._reveal is not None:self._reveal.stop()
        super().hidePopup();self.view().window().setWindowOpacity(1.)

    def _center_rows(self,parent,first,last):
        alignment=Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter if self.expand_popup else Qt.AlignmentFlag.AlignCenter
        for row in range(first,last+1):self.setItemData(row,alignment,Qt.ItemDataRole.TextAlignmentRole)

    def text_rect(self):
        option=QStyleOptionComboBox();self.initStyleOption(option)
        rect=self.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,option,QStyle.SubControl.SC_ComboBoxEditField,self)
        # Balance both the arrow and any color/icon decoration around the text.
        icon_width=option.currentIcon.actualSize(option.iconSize).width()+4 if not option.currentIcon.isNull() else 0
        inset=min(max(rect.left()+icon_width,self.width()-1-rect.right()),self.width()//2)
        rect.setLeft(inset);rect.setRight(self.width()-1-inset)
        return rect

    def paintEvent(self,event):
        option=QStyleOptionComboBox();self.initStyleOption(option)
        painter=QStylePainter(self);text=option.currentText;option.currentText=''
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox,option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel,option)
        rect=self.text_rect()
        painter.drawItemText(rect,Qt.AlignmentFlag.AlignCenter,option.palette,self.isEnabled(),self.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,max(0,rect.width()-4)),QPalette.ColorRole.Text)
