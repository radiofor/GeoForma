"""Choose a compatible runtime without importing Torch in the UI process."""
from importlib.util import find_spec
from .model_catalog import model_spec


def native_available(family):
    if family=='sam3':
        from .sam3_runtime import available
        if available():return True
    from .native_runtime import managed_runtime,lightweight,bundled_release
    if not bundled_release() and managed_runtime():return True
    if lightweight():return False
    modules=('torch','segment_anything') if family=='sam' else ('torch','sam3','triton') if family=='sam3' else ('torch','sam2','hydra','omegaconf')
    try:return all(find_spec(name) is not None for name in modules)
    except (ImportError,ValueError):return False


def resolve_execution(config):
    # Old project preferences are normalized to auto before reaching this point.
    requested=config.get('execution','auto')
    if requested not in ('auto','native'):raise ValueError('GeoForma 仅支持 Windows 原生运行环境。')
    model_spec(config['variant'],config.get('backend','sam'))
    return 'native'
