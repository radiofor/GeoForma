"""Shared status colors and measurements; independent of widgets and workflows."""
from .text import ui_text


SAVED_COLORS=('#176f69','#e5f3ef','#c3e1d8')
REVIEW_COLORS=('#946516','#fff3de','#edd8ad')
STYLES={
    ui_text('status.unsaved'):REVIEW_COLORS,
    ui_text('status.confirmed'):SAVED_COLORS,
    ui_text('status.editing'):('#4058a0','#eef0fc','#cfd6ef'),
    ui_text('reshape.state'):('#8050a0','#f4edf8','#dfcdea'),
}

BADGE_PADDING_X=12
BADGE_PADDING_Y=4
BADGE_TEXT_INSET=8
BADGE_MARGIN_X=4
BADGE_MARGIN_Y=2
BADGE_RADIUS=6


def status_badge_width(metrics,text):
    return metrics.horizontalAdvance(text)+2*BADGE_PADDING_X


def status_column_width(metrics,scrollbar_width):
    # Symmetric clearance keeps captions centered without scrollbar overlap.
    margin=max(2*BADGE_MARGIN_X,scrollbar_width+2)
    return max(status_badge_width(metrics,text) for text in STYLES)+2*margin
