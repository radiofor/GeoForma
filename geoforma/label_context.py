"""Shared rules for labels whose geometry is evaluated together."""


def same_image(left,right):
    """A record without an image identifier belongs to the current context."""
    first=left.get('image_id');second=right.get('image_id')
    return first is None or second is None or first==second
