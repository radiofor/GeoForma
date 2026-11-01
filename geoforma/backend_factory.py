"""Lazy model routing; only the dedicated model process imports adapters."""
from .model_catalog import FAMILIES


def native_backend(family):
    if family=='sam':
        from .backend import SamBackend
        return SamBackend()
    if family in ('sam2','sam2.1'):
        from .sam2_backend import Sam2Backend
        return Sam2Backend(family)
    if family=='sam3':
        from .sam3_backend import Sam3Backend
        return Sam3Backend()
    raise ValueError('此模型版本尚未接入。')


def create_backend(config):
    from .execution_policy import resolve_execution
    family=config.get('backend','sam');execution=resolve_execution(config)
    if family not in FAMILIES or execution!='native':raise ValueError('未知模型或运行环境。')
    return native_backend(family)
