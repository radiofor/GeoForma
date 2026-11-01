"""Deterministic release inventory and license collection; no UI or model imports."""
import hashlib
import re
from pathlib import Path,PurePosixPath
import shutil


def sha256(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def release_inventory(bundle):
    bundle=Path(bundle).resolve();records=[]
    for path in sorted(bundle.rglob('*')):
        if path.is_symlink() or path.is_junction():raise ValueError('发布目录不能包含外部链接：'+str(path))
        if not path.is_file() or path==bundle/'release-manifest.json':continue
        records.append({'path':path.relative_to(bundle).as_posix(),'bytes':path.stat().st_size,'sha256':sha256(path)})
    return records


def verify_release_inventory(bundle,records):
    """Verify the whole payload, including same-size edits and unlisted files."""
    if not isinstance(records,list) or not records:raise ValueError('发布清单为空或格式无效。')
    expected={};names=set()
    for record in records:
        if not isinstance(record,dict):raise ValueError('发布文件记录无效。')
        name=record.get('path');size=record.get('bytes');digest=record.get('sha256')
        if not isinstance(name,str) or not name or '\\' in name or '\0' in name or ':' in name:raise ValueError('发布文件路径无效。')
        path=PurePosixPath(name)
        if path.is_absolute() or str(path)!=name or any(part in ('.','..') for part in path.parts) or name.casefold() in names:raise ValueError('发布文件路径重复或越界。')
        if type(size) is not int or size<0 or not isinstance(digest,str) or not re.fullmatch('[A-Fa-f0-9]{64}',digest):raise ValueError('发布文件大小或校验值无效。')
        names.add(name.casefold());expected[name]=(size,digest.lower())
    actual={item['path']:(item['bytes'],item['sha256']) for item in release_inventory(bundle)}
    if set(actual)!=set(expected):raise ValueError('发布目录文件与清单不一致，存在新增或缺失文件。')
    for name,value in expected.items():
        if actual[name]!=value:raise ValueError('发布文件内容校验失败：'+name)
    return len(actual)


def license_document(path):
    path=Path(path);name=path.name.casefold()
    if path.suffix.casefold() in ('.py','.pyc','.pyo','.dll','.exe','.pyd','.so') or '__pycache__' in path.parts:return False
    return (name.startswith(('license','licence','copying','notice','authors','copyright'))
            or any(part.casefold() in ('licenses','license','licence') for part in path.parts) and path.suffix.casefold() in ('.txt','.md','.rst','.html'))


def collect_licenses(distributions,target):
    target=Path(target);target.mkdir(parents=True,exist_ok=True);packages=[];seen=set()
    for dist in distributions:
        name=dist.metadata['Name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',name):raise ValueError('软件包名称无效。')
        key=name.casefold().replace('_','-')
        if key in seen:continue
        seen.add(key)
        packages.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression',dist.metadata.get('License',''))})
        for file in dist.files or ():
            if not license_document(file):continue
            relative=Path(file)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('许可文件路径无效。')
            source=Path(dist.locate_file(file))
            if source.is_file():
                # Retain subdirectories: different bundled dependencies often use LICENSE.txt.
                destination=target/name/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
    return sorted(packages,key=lambda record:record['name'].casefold())
