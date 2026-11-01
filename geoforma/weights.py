"""Official Meta SAM downloads: managed paths, atomic publishing and cancellation."""
import hashlib,json,os,re,time
from pathlib import Path
from urllib.request import Request
from .network import open_https as urlopen
from urllib.error import HTTPError,URLError
from .domain import data_dir
from .model_catalog import model_spec,MODELS
from .resource_lock import resource_lock as _lock

SPECS={
    'vit_b':('sam_vit_b_01ec64.pth',768),
    'vit_l':('sam_vit_l_0b3195.pth',1024),
    'vit_h':('sam_vit_h_4b8939.pth',1280),
}
BASE='https://dl.fbaipublicfiles.com/segment_anything/'
# Local digests of previously verified official files, not Meta-published signatures.
KNOWN_SHA256={s['variant']:s['sha256'] for s in MODELS if s['backend']=='sam'}


def checkpoint_resource(spec):
    return dict(name=spec['title'],filename=spec['file'],url=spec['url'],sha256=spec['sha256'],bytes=spec['bytes'],source=spec.get('source','Meta 官方源'))


def install_checkpoint(spec,task,source=None):
    """Official files are hash-checked without importing Torch in a Qt worker."""
    from .resource_files import acquire
    from .resource_location import require_resource_dir
    target=acquire(checkpoint_resource(spec),require_resource_dir(data_dir())/'models',task,source)
    task.signals.progress.emit(1,1,'权重已校验 · '+spec['title'])
    return str(target)


def default_checkpoint(variant,backend='sam'):
    spec=model_spec(variant,backend)
    from .distribution import bundled_checkpoint
    from .resource_location import current_resource_dir
    bundled=bundled_checkpoint(spec['file'])
    if bundled:return bundled
    root=data_dir()
    try:resource_root=current_resource_dir(root)
    except (OSError,ValueError):
        # Keep the workbench usable so the user can repair the location. Do not
        # reuse the default resource directory when its configuration is broken.
        resource_root=root/'.unavailable-resource-location'
    return resource_root/'models'/spec['file']


def _progress(task,message,done=0,total=0):
    task.signals.progress.emit(int(100*done/total) if total else 0,100 if total else 0,message)


def _write_json(path,value):
    from .atomic_io import atomic_json
    atomic_json(path,value,indent=2)


def _transfer(url,part,metadata,title,task):
    try:info=json.loads(metadata.read_text())
    except (OSError,ValueError):info={}
    offset=part.stat().st_size if part.exists() and info.get('url')==url else 0
    headers={'User-Agent':'GeoForma/0.1','Accept-Encoding':'identity'}
    if offset:
        headers['Range']=f'bytes={offset}-'
        if info.get('etag'):headers['If-Range']=info['etag']
    source='SAM 3 镜像' if 'huggingface.co/1038lab/sam3/' in url else 'Meta 官方源'
    task.check();_progress(task,f'连接{source}，准备下载模型…')
    try:response=urlopen(Request(url,headers=headers),timeout=15)
    except HTTPError as e:
        if e.code==416 and offset:
            match=re.fullmatch(r'bytes \*/(\d+)',e.headers.get('Content-Range',''))
            if match and offset==int(match[1]):return offset
            part.unlink(missing_ok=True);metadata.unlink(missing_ok=True)
            return _transfer(url,part,metadata,title,task)
        raise
    with response:
        status=response.getcode();length=response.headers.get('Content-Length')
        if status==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match or int(match[1])!=offset:raise ValueError('官方源返回的续传范围不匹配，未写入下载文件。')
            total=int(match[3]);expected_chunk=int(match[2])-offset+1
        elif status==200:
            offset=0;total=int(length) if length else 0;expected_chunk=total
        else:raise ValueError(f'下载响应状态异常：{status}')
        content_type=response.headers.get('Content-Type','').lower()
        if 'text/html' in content_type:raise ValueError('下载地址返回网页而不是权重文件。')
        _write_json(metadata,{'url':url,'etag':response.headers.get('ETag'),'total':total})
        received=0
        with part.open('ab' if offset else 'wb') as stream:
            while True:
                task.check();block=response.read(1024*1024)
                if not block:break
                stream.write(block);received+=len(block);done=offset+received
                text=f'下载权重 · {title} · {done/1048576:.1f}'+(f' / {total/1048576:.1f}' if total else '')+' MiB'
                _progress(task,text,done,total)
            stream.flush();os.fsync(stream.fileno())
        if expected_chunk and received!=expected_chunk:raise OSError('下载未完成，完整分块保留以便续传。')
        if total and part.stat().st_size!=total:raise OSError('权重文件长度不完整，已保留续传文件。')
        task.check();return part.stat().st_size


def _validate(path,variant,task,backend='sam'):
    _progress(task,'验证下载权重的完整性与模型类型…');sha=hashlib.sha256()
    with path.open('rb') as stream:
        while block:=stream.read(4*1024*1024):task.check();sha.update(block)
    digest=sha.hexdigest();expected=KNOWN_SHA256.get(variant) if backend=='sam' else model_spec(variant,backend)['sha256']
    if expected and digest!=expected:raise ValueError('权重文件 SHA256 与已验证的官方文件不一致。')
    # This executes only in the dedicated model process, not a Qt worker thread.
    import torch
    try:state=torch.load(path,map_location='meta',weights_only=True)
    except Exception as e:raise ValueError('下载文件无法作为安全的 PyTorch 权重读取。') from e
    if backend=='sam':
        embed=SPECS[variant][1]
        if not isinstance(state,dict) or tuple(state.get('image_encoder.patch_embed.proj.weight',torch.empty(0)).shape)!=(embed,3,16,16):
            raise ValueError('权重结构与所选 SAM 模型不匹配。')
        if 'prompt_encoder.point_embeddings.0.weight' not in state or 'mask_decoder.iou_token.weight' not in state:
            raise ValueError('权重缺少完整 SAM 提示编码器或掩膜解码器。')
    elif backend=='sam3':
        model=state.get('model',state) if isinstance(state,dict) else None
        if not isinstance(model,dict) or any(k not in model for k in ['tracker.sam_prompt_encoder.point_embeddings.0.weight','tracker.sam_mask_decoder.iou_token.weight']):
            raise ValueError('权重缺少 SAM 3 交互式提示编码器或掩膜解码器。')
        if not any(k.startswith('detector.backbone.') for k in model):raise ValueError('权重缺少 SAM 3 图像编码器。')
    else:
        model=state.get('model') if isinstance(state,dict) else None
        if not isinstance(model,dict) or any(k not in model for k in ['image_encoder.trunk.patch_embed.proj.weight','sam_prompt_encoder.point_embeddings.0.weight','sam_mask_decoder.iou_token.weight']):
            raise ValueError('权重缺少完整 SAM 2 图像、提示编码器或掩膜解码器。')
    del state;task.check();return digest


def ensure_checkpoint(config,task):
    variant=config['variant'];backend=config.get('backend','sam');spec=model_spec(variant,backend);target=default_checkpoint(variant,backend)
    requested=Path(config['checkpoint']) if config.get('checkpoint') else target
    official_names={item['file'] for item in MODELS}
    # A variant change must not keep the previous variant's official file.
    if requested.name in official_names and requested.name!=spec['file']:requested=target
    if requested.is_file():return str(requested)
    from .distribution import bundled_checkpoint
    bundled=bundled_checkpoint(spec['file'])
    if bundled:return str(bundled)
    from .resource_location import require_resource_dir
    require_resource_dir(data_dir())
    target.parent.mkdir(parents=True,exist_ok=True)
    with _lock(target.with_suffix('.download.lock'),task):
        if target.is_file():return str(target)
        url=spec['url'];part=target.with_suffix(target.suffix+'.part');metadata=part.with_suffix(part.suffix+'.json')
        for attempt in range(3):
            try:total=_transfer(url,part,metadata,spec['title'],task);break
            except (URLError,OSError) as e:
                if isinstance(e,HTTPError) and 400<=e.code<500 or attempt==2:
                    source=spec.get('source','Meta 官方')
                    raise RuntimeError(f'无法下载{source}权重，请检查网络后重试；已下载部分保留。详细原因：{e}') from e
                _progress(task,f'下载连接中断，正在续传重试（{attempt+1}/2）…')
                for _ in range(5*(attempt+1)):task.check();time.sleep(.2)
        try:sha=_validate(part,variant,task,backend)
        except ValueError:
            # A corrupt partial cannot safely be resumed on the next attempt.
            part.replace(part.with_name(part.name+'.invalid'));metadata.unlink(missing_ok=True);raise
        manifest={'backend':backend,'variant':variant,'url':url,'bytes':total,'sha256':sha,'sha256_note':'Local digest; Meta README does not publish a full SHA256 for every variant.'}
        _write_json(target.with_suffix('.download.json'),manifest)
        task.check();os.replace(part,target);metadata.unlink(missing_ok=True)
        _progress(task,'权重下载并校验完成 · '+spec['title'],1,1)
        return str(target)
