"""Interruptible visual handoff for an image's label list."""
from PySide6.QtCore import QObject
from ..rendering.frame_transition import FrameTransition


class LabelListTransition(QObject):
    def __init__(self,table):
        super().__init__(table);self.table=table
        self.old_frame=FrameTransition(table,require_raster=False)
        self.old_frame.animation.setDuration(240)

    def capture(self):
        # Empty tables have a background too. Capture it along with any
        # partially faded previous frame so rapid switches stay continuous.
        self.old_frame.capture()

    def reveal(self,changed):
        if changed and self.table.isVisible():self.old_frame.reveal()
        else:self.cancel()

    def cancel(self):self.old_frame.cancel()
