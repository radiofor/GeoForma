"""Stable public service imports; implementations live in inference modules."""
from .inference.client import ModelService
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .inference.engine import ModelEngine

__all__ = ["ModelService", "ModelEngine"]


def __getattr__(name):
    if name == "ModelEngine":
        from .inference.engine import ModelEngine
        return ModelEngine
    raise AttributeError(name)
