"""Real ESRI/S2 manual editing workflow; no SAM inference or accuracy claim."""
import os,json,time,copy,sys
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from main import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication
from shapely.geometry import shape,LineString
from geoforma.storage import load_project
from geoforma.reshape import reshape_intent,reshape_raster
from geoforma.window import MainWindow
from geoforma.domain import new_project
from geoforma.raster import read_rgb
from geoforma.exports import export_vector
from osgeo import ogr


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('experiments/raster_reshape'));args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=True)
    os.environ['GEOFORMA_DATA_DIR']=str(Path('build/reshape_validation').resolve())
    os.environ['GEOFORMA_SETTINGS_FILE']=str((root/'settings.ini').resolve())
    project=load_project('experiments/e2e_vectors/acceptance.geoforma.json');app=QApplication([]);rows=[]
    for family in ['Sentinel-2-RGB','ESRI-RGB']:
        chosen=None
        for label in project['labels']:
            if label['status']!='confirmed':continue
            image=next(i for i in project['images'] if i['id']==label['image_id'])
            if family not in image['path']:continue
            g=shape(label['geometry']);parts=list(g.geoms) if g.geom_type=='MultiPolygon' else [g]
            for part in sorted(parts,key=lambda p:p.area,reverse=True):
                x0,y0,x1,y1=part.bounds
                for fraction in [.1,.2,.3,.4,.6,.7,.8,.9]:
                    y=y0+(y1-y0)*fraction;stroke=[[x0-2,y],[x1+2,y]]
                    try:
                        start=time.perf_counter();result=reshape_raster(image,label['geometry'],stroke,bounds=label.get('box'))
                    except ValueError:continue
                    chosen=(image,label,stroke,result,(time.perf_counter()-start)*1000);break
                if chosen:break
            if chosen:break
        if not chosen:raise AssertionError('No unambiguous edit found: '+family)
        image,label,stroke,result,cpu_ms=chosen;name='s2' if family.startswith('Sentinel') else 'esri'
        w=MainWindow(auto_prepare=False);w.autosave=lambda:None;w.project=new_project(project['model']);w.project['classes']=copy.deepcopy(project['classes'])
        image=copy.deepcopy(image);image['ready']=True;image['mode_sessions']={};image.pop('working_draft',None)
        original=copy.deepcopy(label);original['annotation_mode']='individual';w.project['images']=[image];w.image=image;w.project['labels']=[original]
        w.refresh_classes();w.refresh_images();w.view.set_image(image['width'],image['height']);w.selected_id=original['id'];w.selected_ids={original['id']};w.refresh_labels()
        w.show();app.processEvents();w.zoom_selected();w.render_timer.stop()
        g=shape(original['geometry']);x0,y0,x1,y1=g.bounds;window=[max(0,int(x0)-20),max(0,int(y0)-20),int(x1-x0)+40,int(y1-y0)+40]
        rgb,valid=read_rgb(image,window,image['display_recipe'],900);w.view.show_raster(rgb,valid,window)
        w.begin_reshape();w.reshape_session['stroke']=copy.deepcopy(stroke);w.view.set_reshape_stroke(stroke);w.finish_reshape()
        deadline=time.monotonic()+30
        while w.task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        if w.task or w.reshape_session is not None or w.draft.get('editing_state')!='manual':raise AssertionError('Reshape failed: '+w.last_error)
        w.grab().save(str(root/(name+'_draft.png')));w.confirm();assert w.model_prompts_locked()
        edited=copy.deepcopy(w.project['labels'][0]);assert edited['editing_state']=='manual'
        assert all(x==int(x) and y==int(y) for p in ([shape(edited['geometry'])] if edited['geometry']['type']=='Polygon' else shape(edited['geometry']).geoms) for ring in [p.exterior,*p.interiors] for x,y in ring.coords)
        files=[];task=SimpleNamespace(check=lambda:None,signals=SimpleNamespace(progress=SimpleNamespace(emit=lambda *args:None)))
        for suffix in ['gpkg','shp','geojson']:
            path=root/(name+'.'+suffix);export_vector(image,[edited],path,image['crs'],task,w.project['classes'])
            ds=ogr.Open(str(path));assert ds and ds.GetLayer(0).GetFeatureCount()==1
            feature=ds.GetLayer(0).GetNextFeature();assert feature.GetField('edit_state')=='manual' and feature.GetField('edit_count')==1
            feature=None;ds=None;files.append(path.name)
        w.project_path=root/(name+'.geoforma.json');w.save();w.open_project(w.project_path);w.select_label(original['id']);assert w.model_prompts_locked()
        w.undo_context();assert shape(w.project['labels'][0]['geometry']).equals(shape(original['geometry']))
        w.redo_context();assert w.project['labels'][0]['editing_state']=='manual'
        rows.append({'family':family,'path':image['path'],'image_size':[image['width'],image['height']],'label_id':original['id'],
            'stroke':stroke,'edit_window':result['window'],'added_pixels':result['added_pixels'],'removed_pixels':result['removed_pixels'],
            'cpu_reshape_ms':round(cpu_ms,2),'exports':files,'integer_pixel_edges':True,'manual_lock':True,'project_reopened':True,'undo_redo':True})
        w.image=None;w.dirty=False;w.close()
        deadline=time.monotonic()+5
        while w.render_task and time.monotonic()<deadline:app.processEvents();time.sleep(.002)
        app.processEvents()
    report={'ok':True,'scope':'Real raster and existing SAM polygon workflow, CPU only. No new SAM inference, boundary accuracy or shoreline detection claim.','cases':rows}
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
