"""Logical-pixel sizing shared by the stable workbench panels."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QSizePolicy,QPushButton,QToolButton,QComboBox,QDoubleSpinBox

ROW_HEIGHT=32


def card_layout(card,spacing=6):
    layout=QVBoxLayout(card);layout.setContentsMargins(12,30,12,12);layout.setSpacing(spacing)
    return layout


def reserve_space(widget):
    policy=widget.sizePolicy();policy.setRetainSizeWhenHidden(True);widget.setSizePolicy(policy)


def reserve_scrollbar(area):
    """Keep the gutter width without drawing an inactive full-height handle."""
    area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    bar=area.verticalScrollBar()
    bar.rangeChanged.connect(lambda low,high:bar.setEnabled(high>low))
    bar.setEnabled(bar.maximum()>bar.minimum())


def polish_controls(panel):
    for control in panel.findChildren(QWidget):
        if not isinstance(control,(QPushButton,QToolButton,QComboBox,QDoubleSpinBox)):continue
        locked=control.minimumWidth()==control.maximumWidth()
        retained=control.sizePolicy().retainSizeWhenHidden()
        control.setFixedHeight(ROW_HEIGHT)
        if not locked:control.setMinimumWidth(48 if isinstance(control,(QPushButton,QToolButton)) else 0)
        control.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        if retained:reserve_space(control)
        if isinstance(control,QComboBox):
            control.setMinimumContentsLength(4);control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
