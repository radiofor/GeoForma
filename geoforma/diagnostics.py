"""Machine-readable checks usable without Python or an open GUI on the target PC."""
import platform,sys,threading,traceback
from pathlib import Path
from types import SimpleNamespace

def write_report(path,report):
    from .atomic_io import atomic_json
    atomic_json(path,report,indent=2)

def check_core_exports(directory):
    """Exercise packaged GIS drivers without requiring an inference runtime."""
    import tempfile
    import numpy as np,rasterio
    from osgeo import ogr
    from shapely.geometry import box,mapping
    from .exports import export_raster,export_vector
    from .raster import inspect_source,make_recipe
    task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *a:None)))
    assert np.allclose(np.linalg.solve([[2.,1.],[1.,3.]],[5.,10.]),[1.,3.])
    with tempfile.TemporaryDirectory(prefix='geoforma-export-',dir=directory) as temporary:
        folder=Path(temporary);source=folder/'source.tif'
        with rasterio.open(source,'w',driver='GTiff',height=64,width=64,count=3,dtype='uint8',
                           crs='EPSG:32645',transform=rasterio.transform.from_origin(500000,3000000,10,10)) as ds:
            ds.write(np.full((3,64,64),90,np.uint8))
        image=inspect_source(source);image['model_recipe']=make_recipe(image,[1,2,3])
        labels=[{'id':'self-test','class_id':1,'image_id':image['id'],'status':'confirmed','geometry':mapping(box(10,10,30,30))}]
        for extension in ('gpkg','shp','geojson'):
            path=folder/('labels.'+extension)
            export_vector(image,labels,path,'',task,label_field='class_val')
            dataset=ogr.Open(str(path));assert dataset is not None
            layer=dataset.GetLayer(0);assert layer.GetFeatureCount()==1
            assert layer.GetSpatialRef().GetAuthorityCode(None)==('4326' if extension=='geojson' else '32645')
            dataset=None
        path=folder/'labels.tif';export_raster(image,labels,path,task)
        with rasterio.open(path) as ds:
            assert ds.crs.to_epsg()==32645 and ds.read(1)[15,15]==1 and ds.read(1)[2,2]==0


def self_test(output,raster=None,device='cpu',execution='native',model_id=None,*,core_only=False):
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    report={'ok':False,'version':__import__('geoforma.distribution',fromlist=['VERSION']).VERSION,
            'frozen':bool(getattr(sys,'frozen',False)),'python':sys.version,'platform':platform.platform(),'checks':{}}
    service=None
    try:
        from .package_context import current_package_family,is_store_build
        report.update(package_family=current_package_family(),store_build=is_store_build())
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QLibraryInfo
        app=QApplication.instance() or QApplication([])
        from .branding import application_icon
        assert not application_icon().isNull();report['checks']['qt']=True
        report['qt_plugins']=QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
        import numpy as np,rasterio
        from rasterio.warp import transform
        from osgeo import ogr,osr,gdal
        reference=osr.SpatialReference();assert reference.ImportFromEPSG(4326)==0
        from shapely.geometry import mapping,box
        transform('EPSG:4326','EPSG:3857',[85],[28]);assert ogr.GetDriverByName('GPKG')
        report['checks']['gis']=True;report['gdal']=gdal.VersionInfo();report['rasterio']=rasterio.__version__
        if core_only:
            check_core_exports(Path(output).parent);report['checks']['export']=True
            from .window import MainWindow
            from .ui.resources import ResourceDialog
            from .resource_state import snapshot
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            callback_errors=[];previous_hook=sys.excepthook
            sys.excepthook=lambda kind,value,tb:callback_errors.append(''.join(traceback.format_exception(kind,value,tb)))
            window=MainWindow(auto_prepare=False);window.autosave=lambda:None;window.autosave_timer.stop()
            dialog=ResourceDialog(window);window.show();dialog.show();app.processEvents()
            assert window.resources_action.text()=='资源配置' and dialog.model.count()>0
            assert dialog.location_path.isVisible() and dialog.location_path.text() and dialog.location_path._display_text
            if dialog.tabs.count()>1:
                bar=dialog.tabs.tabBar()
                for index in (1,0):
                    QTest.mouseClick(bar,Qt.MouseButton.LeftButton,pos=bar.tabRect(index).center());app.processEvents()
                    assert dialog.tabs.currentIndex()==index
            size=dialog.size();dialog.progress.model.begin('配置资源','resources');dialog.report(42,100,'下载权重 · 42 / 100 MiB')
            app.processEvents();assert dialog.size()==size
            assert dialog.location_path.isVisible() and dialog.location_path._display_text
            dialog.grab().save(str(Path(output).parent/'resource_setup.png'))
            state=snapshot(window.project['model']);report['resources']={key:state[key]['ready'] for key in ('runtime','weight')}
            QTest.mouseClick(dialog.close_button,Qt.MouseButton.LeftButton);window.dirty=False;window.close();app.processEvents()
            assert not callback_errors, '\n'.join(callback_errors)
            sys.excepthook=previous_hook
            report['checks']['resource_settings']=True;report['checks']['stable_layout']=True;report['checks']['resource_interaction']=True;report['ok']=True;return 0
        import importlib.metadata
        from .runtime_profile import SECURITY_MINIMUMS
        from .native_runtime import managed_runtime,bundled_release
        managed=None if bundled_release() else managed_runtime();external=managed['probe']['versions'] if managed else {}
        report['dependencies']={name:external.get(name) or importlib.metadata.version(name) for name in SECURITY_MINIMUMS}
        from .ui.information import DocumentationDialog,DependencyVersionsDialog
        docs=DocumentationDialog();versions=DependencyVersionsDialog()
        assert '开始标注' in docs.browser.toPlainText() and dict(versions.rows)['GeoForma']==report['version']
        assert dict(versions.rows)['PyTorch']==report['dependencies']['torch']
        docs.deleteLater();versions.deleteLater();report['checks']['settings_information']=True
        from .domain import new_project,prompt_window
        from .inference.client import ModelService
        from .raster import inspect_source,make_recipe
        from .exports import export_vector,export_raster
        progress=SimpleNamespace(emit=lambda *a:None)
        task=SimpleNamespace(cancel_event=threading.Event(),check=lambda:None,signals=SimpleNamespace(progress=progress))
        config=new_project()['model'];config.update(device=device,execution=execution)
        if model_id:
            from .model_catalog import MODELS
            from .weights import default_checkpoint
            spec=next((s for s in MODELS if s['id']==model_id),None)
            if spec is None:raise ValueError('Unknown registered model')
            config.update(backend=spec['backend'],variant=spec['variant'],checkpoint=str(default_checkpoint(spec['variant'],spec['backend'])))
        from .model_catalog import model_spec
        report['model_id']=model_id or model_spec(config['variant'],config['backend'])['id']
        service=ModelService();model=service.prepare_model(config,task);config['checkpoint']=model['checkpoint']
        report['model']=model;report['checks']['spawn_model']=True
        if raster is None:
            raster=Path(output).parent/'self_test_input.tif'
            pixels=np.zeros((3,192,192),np.uint8);pixels[:,40:130,40:140]=np.array([20,90,130])[:,None,None]
            with rasterio.open(raster,'w',driver='GTiff',height=192,width=192,count=3,dtype='uint8',
                crs='EPSG:32645',transform=rasterio.transform.from_origin(500000,3000000,10,10)) as ds:
                ds.write(pixels);ds.colorinterp=(rasterio.enums.ColorInterp.red,rasterio.enums.ColorInterp.green,rasterio.enums.ColorInterp.blue)
        image=inspect_source(raster);image['model_recipe']=make_recipe(image,image['suggested_bands'] or [1,2,3])
        point=[min(90.5,image['width']-.5),min(90.5,image['height']-.5),1]
        request={'window':prompt_window([point]),'points':[point],'box':None}
        answer=service.predict(image,config,request,task);assert answer['choices'];report['checks']['inference']=True
        report['initial_cache_hit']=bool(answer.get('cache_hit'))
        service.close();answer2=service.predict(image,config,request,task)
        report['restored_cache_hit']=bool(answer2.get('cache_hit'))
        first=answer['choices'][0]['geometry'];second=answer2['choices'][0]['geometry'] if answer2['choices'] else None
        if model_id=='sam3_interactive' and second:
            from shapely.geometry import shape
            a,b=shape(first),shape(second);union=a.union(b).area
            report['cache_geometry_iou']=a.intersection(b).area/union if union else 1.0
            consistent=report['cache_geometry_iou']>=.99
        else:consistent=second==first
        assert report['restored_cache_hit'] and consistent;report['checks']['cache_restore']=True
        label={'id':'self-test','class_id':1,'image_id':image['id'],'status':'confirmed','geometry':mapping(box(40,40,80,80)),'source':'self_test','model':config}
        folder=Path(output).parent
        export_vector(image,[label],folder/'self_test_labels.gpkg','',task);export_raster(image,[label],folder/'self_test_labels.tif',task)
        with rasterio.open(folder/'self_test_labels.tif') as ds:
            assert ds.transform==rasterio.transform.Affine(*image['transform']) and ds.width==image['width'] and ds.height==image['height']
        report['checks']['export']=True;report['device']=answer['device'];report['execution']=execution;report['ok']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if 'previous_hook' in locals():sys.excepthook=previous_hook
        if service:service.close()
        write_report(output,report)
    return 0 if report['ok'] else 1
