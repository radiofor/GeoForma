"""Headless cleanup of disposable image caches."""
from .domain import data_dir
from .project_cache import clear_image_cache
from .diagnostics import write_report


def cleanup_command(output=None):
    try:
        from .resource_location import require_resource_dir
        report={'ok':True,'result':clear_image_cache(require_resource_dir(data_dir()))};code=0
    except Exception as error:
        report={'ok':False,'error':str(error)};code=1
    write_report(output or require_resource_dir(data_dir())/'runtime'/'last-command.json',report)
    return code
