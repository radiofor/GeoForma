"""Failure, concurrency and resource regressions for the modularization audit."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box,mapping
from geoforma.atomic_io import atomic_json,atomic_target,read_json
from geoforma.domain import new_project,digest
from geoforma.raster import inspect_source,read_rgb,make_recipe
from geoforma.storage import load_project,save_project
from test_reshape import raster_image,workbench


def test_concurrent_atomic_writers_do_not_share_temporary_files(tmp_path):
    path=tmp_path/'shared.json';barrier=threading.Barrier(6)
    def write(index):
        with atomic_target(path) as temporary:
            temporary.write_text(json.dumps({'writer':index,'values':[index]*5000}),encoding='utf-8')
            barrier.wait(5)
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(write,range(6)))
    result=read_json(path)
    assert result['values']==[result['writer']]*5000
    assert [p.name for p in tmp_path.iterdir()]==['shared.json']


def test_failed_publication_preserves_previous_file_and_removes_temporary(tmp_path):
    path=tmp_path/'project.json';atomic_json(path,{'ok':True})
    with pytest.raises(ValueError):atomic_json(path,{'bad':float('nan')})
    assert read_json(path)=={'ok':True} and len(list(tmp_path.iterdir()))==1


def test_project_save_cannot_overwrite_source_raster(raster_image):
    from pathlib import Path
    path=Path(raster_image['path']);before=path.read_bytes()
    project=new_project();project['images']=[raster_image]
    with pytest.raises(ValueError,match='源影像'):save_project(project,path)
    assert path.read_bytes()==before


@pytest.mark.parametrize('draft',[
    {'points':[[1,2,3]]},{'points':[[1,float('nan'),1]]},
    {'box':[20,20,10,10]},{'window':[0,0,1000000,1000000]},
    {'editing_state':'invalid'},{'pending':'yes'},
])
def test_bad_restored_prompts_are_rejected_before_use(raster_image,tmp_path,draft):
    path=tmp_path/'bad.gfm';project=new_project();project['images']=[raster_image]
    project['workspace']={'image_id':raster_image['id'],'draft':draft}
    path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError):load_project(path)


def test_invalid_session_container_and_nested_history_are_rejected(raster_image,tmp_path):
    project=new_project();project['images']=[raster_image];path=tmp_path/'bad.gfm'
    for sessions in ([],{'other':{}},{'individual':{'undo':[{'points':[[0,float('inf'),1]]}]}}):
        raster_image['mode_sessions']=sessions;path.write_text(json.dumps(project),encoding='utf-8')
        with pytest.raises(ValueError):load_project(path)




def test_mixed_dtype_vrt_and_nodata_are_read_channel_by_channel(tmp_path):
    types=('uint8','uint16','float32');values=(64,1024,.5)
    for index,(dtype,value) in enumerate(zip(types,values),1):
        data=np.full((8,8),value,dtype=dtype)
        if index==3:data[0,0]=np.nan
        with rasterio.open(tmp_path/f'band{index}.tif','w',driver='GTiff',count=1,width=8,height=8,dtype=dtype,crs='EPSG:3857',transform=from_origin(100,200,1,1)) as ds:ds.write(data,1)
    parts=[f'<VRTRasterBand dataType="{dtype}" band="{index}"><ColorInterp>{color}</ColorInterp><SimpleSource><SourceFilename relativeToVRT="1">band{index}.tif</SourceFilename><SourceBand>1</SourceBand></SimpleSource></VRTRasterBand>' for index,dtype,color in [(1,'Byte','Red'),(2,'UInt16','Green'),(3,'Float32','Blue')]]
    vrt=tmp_path/'mixed.vrt';vrt.write_text('<VRTDataset rasterXSize="8" rasterYSize="8"><SRS>EPSG:3857</SRS><GeoTransform>100,1,0,200,0,-1</GeoTransform>'+''.join(parts)+'</VRTDataset>',encoding='utf-8')
    image=inspect_source(vrt);assert len(make_recipe(image,[1,2,3])['ranges'])==3
    image['model_recipe']={'bands':[1,2,3],'ranges':[[0,255],[0,2048],[0,1]]}
    pixels,valid=read_rgb(image,[0,0,8,8])
    assert pixels[1,1].tolist()==[64,127,127]
    assert not valid[0,0] and pixels[0,0].tolist()==[0,0,0]


def test_repeated_grayscale_band_is_read_once(monkeypatch):
    import geoforma.raster as module
    calls=[]
    class Source:
        width=8;height=8;count=1;nodata=None
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,band,**kwargs):calls.append(band);return np.full((8,8),90,np.uint8)
        def read_masks(self,band,**kwargs):return np.full((8,8),255,np.uint8)
        def tags(self):return {}
    monkeypatch.setattr(module.rasterio,'open',lambda *a:Source())
    pixels,valid=read_rgb({'path':'unused','model_recipe':{'bands':[1,1,1],'ranges':[[0,255]]*3}},[0,0,8,8])
    assert calls==[1] and valid.all() and (pixels==90).all()


def test_render_completion_does_not_repopulate_closed_cache():
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from geoforma.rendering.raster_queue import RasterRenderQueue
    import time
    app=QApplication.instance() or QApplication([]);pool=QThreadPool();started=threading.Event();release=threading.Event()
    def reader(*args):
        started.set();release.wait(3);return np.zeros((8,8,3),np.uint8),np.ones((8,8),bool)
    queue=RasterRenderQueue(pool,reader);queue.request({'id':'image','path':'unused','display_recipe':{}},1,(0,0,8,8),8,True)
    assert started.wait(3);queue.close();release.set();deadline=time.monotonic()+4
    while queue.task and time.monotonic()<deadline:app.processEvents();QTest.qWait(2)
    assert queue.task is None and not queue.cache and queue.cache_bytes==0
    pool.waitForDone()


def test_failed_spawn_closes_pipe_endpoints(monkeypatch):
    import multiprocessing
    from geoforma.inference.client import ModelService
    closed=[]
    parent=SimpleNamespace(close=lambda:closed.append('parent'))
    child=SimpleNamespace(close=lambda:closed.append('child'))
    class Process:
        pid=None
        def start(self):raise OSError('spawn unavailable')
        def close(self):closed.append('process')
    context=SimpleNamespace(Pipe=lambda:(parent,child),Event=threading.Event,Process=lambda **kw:Process())
    monkeypatch.setattr(multiprocessing,'get_context',lambda *a:context)
    service=ModelService()
    with pytest.raises(OSError,match='spawn unavailable'):service._start()
    assert set(closed)=={'parent','child','process'} and service.process is None and service.connection is None
    service.close()


def test_worker_releases_backend_when_pipe_breaks(monkeypatch):
    from geoforma.inference import engine,worker
    closed=[]
    backend=SimpleNamespace(prepare_model=lambda *a:{},backend=None,close=lambda:closed.append('backend'))
    monkeypatch.setattr(engine,'ModelEngine',lambda:backend)
    class Connection:
        def recv(self):return 'prepare_model',({},)
        def send(self,message):
            if message[0]!='ready':raise BrokenPipeError()
        def close(self):closed.append('pipe')
    worker._model_process(Connection(),threading.Event())
    assert closed==['backend','pipe']


@pytest.mark.parametrize('damage',['name','bands','dtypes','crs','fingerprint','source_files','recipe','runs','range','view'])
def test_bad_project_cannot_partially_replace_live_workbench(workbench,damage):
    w,app,tmp=workbench;original=w.project;bad=copy.deepcopy(original)
    image=bad['images'][0]
    if damage=='name':image['name']=None
    elif damage=='bands':image['bands']=0
    elif damage=='dtypes':image['dtypes']='float32'
    elif damage=='crs':image['crs']={}
    elif damage=='fingerprint':image['fingerprint']=None
    elif damage=='source_files':image['source_files']=-1
    elif damage=='recipe':image['model_recipe']['bands']=[1,2,999]
    elif damage=='runs':image['candidate_runs']={'invalid':[]}
    elif damage=='range':bad['workspace']={'candidate_range':[0,'bad',False]}
    elif damage=='view':image['mode_sessions']={'individual':{'view':[0,0,float('inf'),10]}}
    path=tmp/'bad_project.gfm';path.write_text(json.dumps(bad),encoding='utf-8')
    errors=[];w.error=errors.append;w.open_project(path)
    assert errors and w.project is original and w.project['labels'][0]['id']=='target'
