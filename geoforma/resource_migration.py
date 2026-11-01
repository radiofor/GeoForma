"""Recoverable, verified relocation of app-managed resource files."""
import hashlib,os,re,shutil,time
from pathlib import Path
from .atomic_io import atomic_json,atomic_target,read_json
from .domain import data_dir
from .resource_location import (CONFIG,FOLDER,MARKER,MARKER_CONTENT,current_resource_dir,
                                default_resource_dir,prepare_resource_parent,require_resource_dir)

JOURNAL='resource-migration.json'
BLOCK=4*1024*1024


def pending_migration():
    path=data_dir()/JOURNAL
    if not path.exists():return None
    if path.is_symlink() or path.is_junction():raise ValueError('迁移记录不能是链接。')
    record=read_json(path,max_bytes=64*1024*1024)
    if not isinstance(record,dict) or record.get('kind')!='geoforma-resource-migration-v1':raise ValueError('迁移记录无效。')
    return record


def _progress(task,stage,current,total):
    task.check()
    now=time.monotonic();previous=getattr(task,'_migration_progress',None)
    if previous and previous[0]==stage and (not total or current<total) and now-previous[1]<0.08:return
    task._migration_progress=(stage,now)
    task.signals.progress.emit(current,total,stage)


def _hash(path,task,progress=None):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno())
        while chunk:=stream.read(BLOCK):
            task.check();digest.update(chunk)
            if progress:progress(len(chunk))
        after=os.fstat(stream.fileno())
    current=path.stat()
    if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino) or (after.st_size,after.st_mtime_ns,after.st_ino)!=(current.st_size,current.st_mtime_ns,current.st_ino):
        raise ValueError('迁移文件在校验期间发生变化：'+str(path))
    return digest.hexdigest()


def _safe(root,relative):
    rel=Path(relative)
    reserved={'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}
    if (rel.is_absolute() or not rel.parts or any(part in ('.','..') or part.endswith((' ','.')) or part.split('.')[0].casefold() in reserved or any(char in part for char in ':<>"|?*\0') for part in rel.parts)):
        raise ValueError('迁移路径无效。')
    path=root
    for part in rel.parts:
        path=path/part
        if path.is_symlink() or path.is_junction():raise ValueError('迁移路径包含链接。')
    if not path.resolve().is_relative_to(root):raise ValueError('迁移路径超出资源目录。')
    return path


def _files(root):
    """Only managed resource trees; unrelated root files and locks stay put."""
    from .model_catalog import MODELS
    from .project_cache import FILE_PATTERN
    models={item['file'] for item in MODELS}
    found=[]
    for relative in ('models','cache','runtime/native-v1','runtime/exchange','recovery'):
        folder=_safe(root,relative)
        if not folder.exists():continue
        if not folder.is_dir():raise ValueError('资源目录结构无效：'+relative)
        for base,dirs,files in os.walk(folder,followlinks=False):
            base=Path(base)
            for name in dirs:
                p=base/name
                if p.is_symlink() or p.is_junction():raise ValueError('资源目录包含链接：'+str(p))
            for name in files:
                path=base/name;rel=path.relative_to(root);parts=rel.parts
                if path.is_symlink() or path.is_junction():raise ValueError('资源文件包含链接：'+str(path))
                if name.endswith('.lock') or name.startswith('.cache-session'):continue
                if relative=='models':
                    if len(parts)!=2 or not any(name==n or name.startswith(n+'.') or name.startswith(Path(n).stem+'.download.') for n in models):continue
                elif relative=='cache':
                    if len(parts)==2 and name=='active-project.json':pass
                    elif len(parts)==3 and parts[1] in ('features','automatic') and FILE_PATTERN.fullmatch(name):pass
                    else:continue
                elif relative=='recovery':
                    if len(parts)!=2 or name not in ('untitled.geoforma.json','untitled.geoforma.json.autosave'):continue
                elif relative=='runtime/exchange':
                    if len(parts)==4 and re.fullmatch(r'worker_[A-Za-z0-9_-]+',parts[2]) and name=='worker.log':pass
                    elif len(parts)==5 and re.fullmatch(r'worker_[A-Za-z0-9_-]+',parts[2]) and re.fullmatch('[a-f0-9]{32}',parts[3]) and name in ('worker.log','input.npz','output.npz'):pass
                    else:continue
                elif len(parts)>=3 and parts[2] not in ('downloads','current.json'):
                    if not re.fullmatch('[a-f0-9]{32}',parts[2]):continue
                    generation=_safe(root,Path('runtime/native-v1')/parts[2])
                    if not (generation/'installed.json').is_file() and not (generation/'.geoforma-native-stage').is_file():continue
                if not path.is_file():raise ValueError('资源文件类型无效。')
                found.append(rel.as_posix())
    for name in ('errors.log','worker-startup.log'):
        p=_safe(root,name)
        if p.is_file():found.append(name)
    return sorted({name for name in found if _allowed(name)})


def _roots(source,target):
    source=Path(source);target=Path(target)
    if not source.is_absolute() or not target.is_absolute() or source.is_symlink() or source.is_junction() or target.is_symlink() or target.is_junction():raise ValueError('迁移根目录无效。')
    source=source.resolve();target=target.resolve()
    if source==target:return source,target
    if source.is_relative_to(target) or target.is_relative_to(source):raise ValueError('新旧资源目录不能相互包含。')
    return source,target


def _allowed(name):
    from .model_catalog import MODELS
    from .project_cache import FILE_PATTERN
    from .native_runtime import catalog
    path=Path(name);parts=path.parts
    if path.is_absolute() or not parts or any(part in ('..','.') for part in parts):return False
    if len(parts)==1:return name in ('errors.log','worker-startup.log')
    if parts[0]=='models' and len(parts)==2:
        return any(parts[1] in (s['file'],s['file']+'.part',s['file']+'.part.json',s['file']+'.part.invalid',Path(s['file']).stem+'.download.json') for s in MODELS)
    if parts[0]=='cache':
        return (len(parts)==2 and parts[1]=='active-project.json') or (len(parts)==3 and parts[1] in ('features','automatic') and bool(FILE_PATTERN.fullmatch(parts[2])))
    if parts[0]=='recovery':return len(parts)==2 and parts[1] in ('untitled.geoforma.json','untitled.geoforma.json.autosave')
    if len(parts)>=4 and parts[:2]==('runtime','exchange') and re.fullmatch(r'worker_[A-Za-z0-9_-]+',parts[2]):
        return (len(parts)==4 and parts[3]=='worker.log') or (len(parts)==5 and bool(re.fullmatch('[a-f0-9]{32}',parts[3])) and parts[4] in ('worker.log','input.npz','output.npz'))
    if len(parts)>=3 and parts[:2]==('runtime','native-v1'):
        if len(parts)==3 and parts[2]=='current.json':return True
        if re.fullmatch('[a-f0-9]{32}',parts[2]):return len(parts)>=4 and not parts[-1].endswith('.lock')
        if parts[2]=='downloads' and len(parts)==4:
            names=[w['filename'] for profile in catalog()['profiles'].values() for w in profile['wheels']]
            return any(parts[-1] in (n,n+'.part',n+'.part.json') for n in names)
    return False


def _validate(record,source,target):
    root=data_dir().resolve()
    for path in (source,target):
        if path==root:continue
        marker=path/MARKER
        if path.name.casefold()!=FOLDER.casefold() or marker.is_symlink() or marker.is_junction() or not marker.is_file() or marker.read_text(encoding='utf-8')!=MARKER_CONTENT:
            raise ValueError('迁移目录归属无效。')
    entries=record.get('files')
    if not isinstance(entries,list) or record.get('phase') not in ('copy','committed'):raise ValueError('迁移记录无效。')
    seen=set()
    for item in entries:
        if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not _allowed(item['path']) or type(item.get('bytes')) is not int or item['bytes']<0 or not isinstance(item.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',item['sha256']):raise ValueError('迁移文件记录无效。')
        _safe(source,item['path']);_safe(target,item['path'])
        key=item['path'].casefold()
        if key in seen:raise ValueError('迁移文件记录重复。')
        seen.add(key)
    return entries


def migrate_resources(parent,task):
    if pending_migration():raise RuntimeError('存在未完成的迁移，请先继续。')
    source=require_resource_dir().resolve();target=prepare_resource_parent(parent)
    return _begin(source,target,task)


def migrate_to_default(task):
    if pending_migration():raise RuntimeError('存在未完成的迁移，请先继续。')
    source=require_resource_dir().resolve();root=data_dir().resolve();target=default_resource_dir(root).resolve()
    if target!=root:target=prepare_resource_parent(target)
    return _begin(source,target,task)


def _begin(source,target,task):
    source,target=_roots(source,target)
    if source==target:return {'source':str(source),'destination':str(target)}
    from .session_guard import active_resource_lease
    lease=active_resource_lease()
    if lease is None:raise RuntimeError('迁移需要活动资源会话。')
    with lease.transition(target):
        # Check after taking the destination lease, so another session cannot
        # introduce managed files between the conflict check and the copy.
        if _files(target):raise ValueError('目标资源目录已有数据，请选择空目录。')
        names=_files(source);entries=[];total=sum(_safe(source,name).stat().st_size for name in names);done=0
        if shutil.disk_usage(target).free<total:raise OSError('目标资源目录可用空间不足。')
        for index,name in enumerate(names):
            _progress(task,'检查源文件',int(done*100/max(1,total)),100)
            def advance(count):
                nonlocal done
                done+=count;_progress(task,'检查源文件',int(done*100/max(1,total)),100)
            path=_safe(source,name);info=path.stat();digest=_hash(path,task,advance)
            if path.stat().st_size!=info.st_size or path.stat().st_mtime_ns!=info.st_mtime_ns:raise RuntimeError('源文件在迁移期间发生变化。')
            entries.append({'path':name,'bytes':info.st_size,'sha256':digest})
        record={'kind':'geoforma-resource-migration-v1','source':str(source),'destination':str(target),'phase':'copy','files':entries}
        atomic_json(data_dir()/JOURNAL,record,indent=2)
        return _execute(record,task)


def resume_migration(task):
    record=pending_migration()
    if not record:raise ValueError('没有待恢复的迁移。')
    source,target=_roots(record['source'],record['destination'])
    from .session_guard import active_resource_lease
    from .resource_lock import try_resource_lock
    lease=active_resource_lease()
    if lease is None:raise RuntimeError('迁移需要活动资源会话。')
    current=current_resource_dir().resolve()
    if current==source:
        lease.ensure(source)
        with lease.transition(target):return _execute(record,task)
    if current==target and lease.root==source:
        with lease.transition(target):return _execute(record,task)
    if current==target:
        lease.ensure(target)
        with try_resource_lock(source/'.cache-session.lock') as acquired:
            if not acquired:raise RuntimeError('原资源目录正在使用，无法继续清理。')
            return _execute(record,task)
    raise ValueError('资源位置与迁移记录不一致。')


def _execute(record,task):
    source,target=_roots(record['source'],record['destination']);entries=record['files'];journal=data_dir()/JOURNAL
    entries=_validate(record,source,target)
    # Always verify existing target files before using or deleting originals.
    total=sum(item['bytes'] for item in entries);done=0
    for index,item in enumerate(entries):
        name=item['path'];src=_safe(source,name);dst=_safe(target,name)
        _progress(task,'复制并校验资源',int(done*100/max(1,total)),100)
        if dst.exists():
            if not dst.is_file() or dst.stat().st_size!=item['bytes'] or _hash(dst,task)!=item['sha256']:raise ValueError('目标文件冲突：'+name)
        else:
            if not src.is_file() or src.stat().st_size!=item['bytes'] or _hash(src,task)!=item['sha256']:raise ValueError('原文件缺失或已改变：'+name)
            dst.parent.mkdir(parents=True,exist_ok=True)
            with atomic_target(dst) as temp:
                with src.open('rb') as inp,temp.open('wb') as out:
                    while chunk:=inp.read(BLOCK):
                        task.check();out.write(chunk);done+=len(chunk)
                        _progress(task,'复制并校验资源',int(done*100/max(1,total)),100)
                if _hash(temp,task)!=item['sha256']:raise ValueError('复制校验失败：'+name)
            continue
        done+=item['bytes']
    _progress(task,'复制并校验资源',100,100)
    task.check()
    root=data_dir().resolve()
    history_path=root/'resource-migration-history.json'
    history=read_json(history_path) if history_path.is_file() else {'kind':'geoforma-resource-migration-history-v1','migrations':[]}
    if history.get('kind')!='geoforma-resource-migration-history-v1' or not isinstance(history.get('migrations'),list):raise ValueError('迁移历史无效。')
    item={'source':str(source),'destination':str(target),'models':[e['path'] for e in entries if e['path'].startswith('models/')],
          'recoveries':[e['path'] for e in entries if e['path'].startswith('recovery/')]}
    if item not in history['migrations']:history['migrations'].append(item);atomic_json(history_path,history,indent=2)
    atomic_json(root/CONFIG,{'kind':'geoforma-resource-location-v1','path':str(target)},indent=2)
    record['phase']='committed';atomic_json(journal,record,indent=2)
    for index,item in enumerate(entries):
        _progress(task,'清理已迁移资源',index,len(entries))
        src=_safe(source,item['path']);dst=_safe(target,item['path'])
        if not src.exists():continue
        if not src.is_file() or src.stat().st_size!=item['bytes'] or _hash(src,task)!=item['sha256'] or _hash(dst,task)!=item['sha256']:
            raise ValueError('源文件已改变，保留文件：'+item['path'])
        src.unlink()
    if entries:_progress(task,'清理已迁移资源',len(entries),len(entries))
    journal.unlink()
    return {'source':str(source),'destination':str(target)}
