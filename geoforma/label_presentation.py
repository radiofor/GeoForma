"""Derive label presentation from authoritative geometry and view options."""


def presentation_batch(labels,fill,smoothing,image=None,task=None,cache=None,cache_epoch=None):
    """Apply the same non-destructive fill and smoothing for display and export."""
    output=list(labels)
    if smoothing.get('enabled'):
        from .smoothing import smooth_batch
        output=smooth_batch(output,smoothing['value'],image,task,cache,cache_epoch)
    if fill:
        from .hole_filling import fill_label_holes
        output=fill_label_holes(output,task)
    return output
