"""Conservative cleanup of obsolete, application-owned download remnants."""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import re
import time
from .project_cache import checked_directory
from .resource_lock import try_resource_lock

PARTIAL_AGE=24*60*60
INVALID_AGE=7*24*60*60
TEMP_AGE=7*24*60*60
RESUME_AGE=30*24*60*60
WHEEL_CACHE_AGE=30*24*60*60


def _old_file(path, cutoff):
    return not path.is_symlink() and not path.is_junction() and path.is_file() and path.stat().st_mtime<=cutoff


def _same_file(path, before):
    after=path.stat()
    return (after.st_size,after.st_mtime_ns)==(before.st_size,before.st_mtime_ns)


def _verified(path,spec,check):
    if path.is_symlink() or path.is_junction() or not path.is_file():return False
    before=path.stat()
    if before.st_size!=spec['bytes']:return False
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(4*1024*1024):check();sha.update(block)
    return sha.hexdigest()==spec['sha256'] and _same_file(path,before)


def clean_download_remnants(root,task,*,apply=False,now=None,only_model=None):
    """Clean recognized, inactive resource remnants without touching source data.

    Incomplete downloads remain resumable for 30 days after their last change.
    Both download APIs' locks are held before touching model files; busy
    resources are skipped. Complete cached wheels require an installed runtime
    and a matching hash before removal.
    """
    from .model_catalog import MODELS
    from .native_runtime import catalog
    root=Path(root).resolve();now=time.time() if now is None else now
    report={'applied':apply,'files':[],'directories':[],'bytes':0,'skipped':[]}
    groups=[('models',[dict(filename=s['file'],bytes=s['bytes'],sha256=s['sha256']) for s in MODELS],True)]
    wheels={w['filename']:w for profile in catalog()['profiles'].values() for w in profile['wheels']}
    groups.append(('runtime/native-v1/downloads',list(wheels.values()),False))
    for relative,specs,is_model in groups:
        task.check()
        try:folder=checked_directory(root,relative)
        except (OSError,ValueError):report['skipped'].append(relative);continue
        if not folder.is_dir():continue
        try:entries=list(folder.iterdir())
        except OSError:report['skipped'].append(relative);continue
        for spec in specs:
            task.check();name=spec['filename']
            if only_model is not None and (not is_model or name!=only_model):continue
            if Path(name).name!=name:continue
            target=folder/name;part=target.with_suffix(target.suffix+'.part')
            invalid=part.with_suffix(part.suffix+'.invalid')
            metadata=part.with_suffix(part.suffix+'.json')
            try:
                has_partial=_old_file(part,now-PARTIAL_AGE)
                orphan_metadata=_old_file(metadata,now-PARTIAL_AGE) and not part.exists() and not part.is_symlink()
                has_invalid=is_model and _old_file(invalid,now-INVALID_AGE)
                temp_targets=[target.name,metadata.name]
                if is_model:temp_targets.append(target.with_suffix('.download.json').name)
                temp_patterns=[re.compile(r'\.'+re.escape(item)+r'\.[a-z0-9_]{8}\.tmp') for item in temp_targets]
                temps=[path for path in entries if any(pattern.fullmatch(path.name) for pattern in temp_patterns) and _old_file(path,now-TEMP_AGE)]
                old_wheel=not is_model and _old_file(target,now-WHEEL_CACHE_AGE)
                if not has_partial and not orphan_metadata and not has_invalid and not temps and not old_wheel:continue
                locks=([target.with_suffix('.download.lock'),target.with_suffix(target.suffix+'.lock')] if is_model
                       else [folder.parent/'install.lock',target.with_suffix(target.suffix+'.lock')])
                with ExitStack() as stack:
                    if apply and not all(stack.enter_context(try_resource_lock(lock)) for lock in locks):continue
                    task.check()
                    removable=[path for path in temps if _old_file(path,now-TEMP_AGE)]
                    eligible_wheel=False
                    if old_wheel:
                        from .housekeeping_stages import installed_wheels
                        eligible_wheel=name in installed_wheels(folder.parent)
                    verified=_verified(target,spec,task.check) if has_partial or orphan_metadata or eligible_wheel else False
                    metadata_missing=not metadata.exists() and not metadata.is_symlink() and not metadata.is_junction()
                    expired=has_partial and _old_file(part,now-RESUME_AGE) and (metadata_missing or _old_file(metadata,now-RESUME_AGE))
                    if has_partial and (verified or expired) and _old_file(part,now-PARTIAL_AGE):removable.append(part)
                    if _old_file(metadata,now-PARTIAL_AGE) and (part in removable or not part.exists() and not part.is_symlink()) and (verified or _old_file(metadata,now-INVALID_AGE)):removable.append(metadata)
                    if has_invalid and _old_file(invalid,now-INVALID_AGE):removable.append(invalid)
                    if eligible_wheel and _old_file(target,now-WHEEL_CACHE_AGE) and verified:removable.append(target)
                    for path in removable:
                        task.check()
                        if path.is_symlink() or path.is_junction() or not path.is_file():continue
                        before=path.stat()
                        if not _same_file(path,before):continue
                        if apply:path.unlink()
                        report['files'].append(path.relative_to(root).as_posix());report['bytes']+=before.st_size
            except (OSError,ValueError):report['skipped'].append((Path(relative)/name).as_posix())
    if only_model is None:
        from .housekeeping_stages import clean_abandoned_stages
        stages=clean_abandoned_stages(root,task,apply=apply,now=now)
        report['directories'].extend(stages['directories']);report['bytes']+=stages['bytes'];report['skipped'].extend(stages['skipped'])
    return report
