"""Detached raster metadata for background operations."""
import copy


def image_snapshot(image):
    """Exclude mutable workbench sessions and display-only references."""
    return copy.deepcopy({key:value for key,value in image.items() if key not in ('working_draft','mode_sessions','_reference')})
