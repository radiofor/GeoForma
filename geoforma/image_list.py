"""Expand local VRT references into independent TIFF imports; no raster pixels read."""
from dataclasses import dataclass,field
from pathlib import Path
from xml.etree import ElementTree

RASTER_SUFFIXES={'.tif','.tiff'}
IMPORT_SUFFIXES=RASTER_SUFFIXES|{'.vrt'}
MAX_BYTES=8*1024*1024
MAX_IMAGES=100_000
MAX_TOTAL_VRT_BYTES=64*1024*1024
MAX_VRT_DEPTH=32


class _ImportLimitReached(ValueError):pass


@dataclass
class ImportPlan:
    entries:list=field(default_factory=list)
    errors:list=field(default_factory=list)
    duplicates:int=0

    def summary(self,imported):
        return f'成功 {imported} 幅'+(f' · 重复 {self.duplicates} 项' if self.duplicates else '')+(f' · 失败 {len(self.errors)} 项' if self.errors else '')


def read_vrt_sources(path,check=lambda:None):
    path=Path(path)
    with path.open('rb') as stream:payload=stream.read(MAX_BYTES+1)
    if len(payload)>MAX_BYTES:raise ValueError('单份 VRT 不能超过 8 MiB。')
    try:
        text=payload.decode('utf-8-sig')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('VRT 不支持外部声明或实体。')
        root=ElementTree.fromstring(text)
    except (ElementTree.ParseError,UnicodeError) as error:raise ValueError(f'VRT XML 格式无效：{error}') from error
    if root.tag.rsplit('}',1)[-1]!='VRTDataset':raise ValueError('请选择栅格 VRT 文件。')
    sources=[];seen=set()
    for index,node in enumerate(root.iter()):
        if index%32==0:check()
        if node.tag.rsplit('}',1)[-1] not in ('SourceFilename','SourceDataset'):continue
        value=(node.text or '').strip()
        if not value or value.startswith(('/vsi','http:','https:','s3:','gs:','<')):raise ValueError('VRT 必须引用本地 TIF/TIFF 或 VRT 文件。')
        source=Path(value)
        if not source.is_absolute() and node.get('relativeToVRT')=='1':source=path.parent/source
        source=source.resolve();key=str(source).casefold()
        if key not in seen:sources.append(source);seen.add(key)
    if not sources:raise ValueError('VRT 中没有可展开的影像文件引用。')
    return sources


def plan_import(paths,existing=(),check=lambda:None):
    plan=ImportPlan();seen={str(Path(p).resolve()).casefold() for p in existing};seen_vrts=set();vrt_bytes=0
    def visit(path,chain=()):
        nonlocal vrt_bytes
        check();path=Path(path).resolve();key=str(path).casefold()
        if path.suffix.lower()=='.vrt':
            if key in {str(p).casefold() for p in chain}:raise ValueError('VRT 存在循环引用。')
            if len(chain)>=MAX_VRT_DEPTH:raise ValueError('VRT 嵌套层级过深。')
            if key in seen_vrts:plan.duplicates+=1;return
            seen_vrts.add(key);vrt_bytes+=path.stat().st_size
            if vrt_bytes>MAX_TOTAL_VRT_BYTES:raise _ImportLimitReached('本次 VRT 总大小超过 64 MiB，请分批导入。')
            for source in read_vrt_sources(path,check):
                try:visit(source,(*chain,path))
                except _ImportLimitReached:raise
                except (ValueError,OSError) as error:plan.errors.append(f'{source}: {error}')
            return
        if path.suffix.lower() not in RASTER_SUFFIXES:raise ValueError('仅支持 TIF、TIFF 和 VRT；不再支持自定义 YAML/list 清单。')
        if key in seen:plan.duplicates+=1;return
        if len(plan.entries)>=MAX_IMAGES:raise _ImportLimitReached(f'一次导入最多包含 {MAX_IMAGES} 幅影像。')
        seen.add(key)
        metadata={'source':str(chain[0]),'source_paths':[str(p) for p in chain]} if chain else {}
        plan.entries.append((str(path),metadata))
    for value in paths:
        try:
            if not isinstance(value,(str,Path)) or not str(value).strip() or chr(0) in str(value):raise ValueError('影像路径不能为空。')
            visit(value)
        except _ImportLimitReached as error:plan.errors.append(str(error));return plan
        except (ValueError,OSError) as error:plan.errors.append(f'{value}: {error}')
    return plan
