"""Explicit visual-review prompts for residual cloud, moraine and village regions."""
import json,os,sys,time,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));OUT=ROOT/'experiments/e2e_vectors'
os.environ['GEOFORMA_DATA_DIR']=str(OUT/'data');os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from main import configure_runtime
configure_runtime()
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtCore import QSettings,QRectF,Qt
from shapely.geometry import shape,Point
from shapely.affinity import affine_transform
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from osgeo import ogr
from geoforma.window import MainWindow

def main():
    app=QApplication([]);w=MainWindow(auto_prepare=False);w.settings=QSettings('GeoForma','GeoFormaTests');errors=[];w.error=errors.append;w.show()
    def wait():
        deadline=time.monotonic()+120;idle=0
        while idle<4:
            app.processEvents();time.sleep(.01)
            if errors:raise RuntimeError('\n'.join(errors))
            active=w.task or w.render_task or w.candidate_task or w.render_timer.isActive() or w.autosave_task
            idle=0 if active else idle+1
            if time.monotonic()>deadline:raise TimeoutError('Review task')
    cases=[
        ('ESRI-RGB','BX1517_BY0858',[3475.5,4194.5], [3457,4174,3500,4224],
         [[3475.5,4194.5,1],[3481.5,4201.5,1],[3448.5,4180.5,0],[3498.5,4178.5,0],[3504.5,4214.5,0],[3470.5,4232.5,0],[3453.5,4210.5,0],[3475.5,4168.5,0]]),
        ('Sentinel-2-RGB-2025','BX1516_BY0858',[1860.5,612.5],[1844,591,1879,624],
         [[1860.5,606.5,1],[1853.5,606.5,1],[1866.5,600.5,1],[1840.5,605.5,0],[1854.5,591.5,0],[1880.5,603.5,0],[1863.5,626.5,0],[1869.5,619.5,0],[1885.5,613.5,0]]),
        ('Sentinel-2-RGB-2025','BX1516_BY0858',[1143.5,1516.5],[1065,1484,1209,1539],
         [[1143.5,1516.5,1],[1103.5,1511.5,1],[1173.5,1515.5,1],[1142.5,1475.5,0],[1143.5,1550.5,0],[1104.5,1475.5,0],[1088.5,1545.5,0],[1240.5,1510.5,0],[1175.5,1560.5,0],[1158.5,1474.5,0]]),
        ('ESRI-RGB','BX1517_BY0858',[2867,4554],[2350,4140,3380,4970],
         [[2867.5,4554.5,1],[2760.5,4500.5,1],[3180.5,4280.5,0],[3210.5,4260.5,0],[3290.5,4300.5,0],[2450.5,4340.5,0],[3100.5,4990.5,0]])]
    rows=[]
    try:
        w.open_project(OUT/'acceptance.geoforma.json',True);wait()
        for provider,tile,anchor,bounds,points in cases:
            w.clear_draft();index=next(i for i,image in enumerate(w.project['images']) if provider in image['path'] and Path(image['path']).stem==tile);w.images.setCurrentRow(index);wait();w.tabs.setCurrentIndex(0)
            chosen=min([l for l in w.current_labels() if l['status']=='confirmed'],key=lambda l:shape(l['geometry']).distance(Point(*anchor)))
            previous=shape(chosen['geometry']);w.select_items('labels',[chosen['id']]);w.edit_selected(locate=False);w.add_box(bounds)
            for point in points:w.add_point(*point)
            w.reset_prior();wait();assert w.draft.get('geometry')
            after=shape(w.draft['geometry'])
            # These are explicitly single-lake review cases. Rejected detached
            # land/cloud pieces become negative prompts, never silently deleted.
            parts=list(after.geoms) if after.geom_type=='MultiPolygon' else [after]
            for part in parts:
                if not any(part.covers(Point(x,y)) for x,y,sign in points if sign):
                    p=part.representative_point();w.add_point(p.x,p.y,0);points.append([p.x,p.y,0])
            if len(parts)>1:w.predict();wait();after=shape(w.draft['geometry'])
            misses=[p for p in points if after.covers(Point(p[0],p[1]))!=(p[2]==1)]
            (OUT/'quality'/f'review_{provider}_{tile}.json').write_text(json.dumps({'misses':misses,'points':points,'geometry':w.draft['geometry']},indent=2))
            assert not misses,misses
            x0,y0,x1,y1=bounds;pad=max(x1-x0,y1-y0)*.7;w.view.fitInView(QRectF(x0-pad,y0-pad,x1-x0+2*pad,y1-y0+2*pad),Qt.AspectRatioMode.KeepAspectRatio);w.view.viewportChanged.emit();wait()
            folder=OUT/('esri' if provider=='ESRI-RGB' else 's2')/tile;number=1 if anchor[0]<5000 and provider=='ESRI-RGB' and anchor[1]<4300 or provider!='ESRI-RGB' and anchor[0]<1500 else 2
            w.grab().save(str(folder/f'reviewed_target_{number}.png'));w.confirm();wait();w.clear_draft()
            rows.append({'image':w.image['path'],'label_id':chosen['id'],'before_pixels':previous.area,'after_pixels':after.area,'positive_points':sum(p[2] for p in points),'negative_points':sum(not p[2] for p in points)})
            print(rows[-1],flush=True)
        # All twelve vector outputs are refreshed through the normal UI export command.
        for i,image in enumerate(w.project['images']):
            w.images.setCurrentRow(i);wait();high='ESRI-RGB' in image['path'];folder=OUT/('esri' if high else 's2')/Path(image['path']).stem
            labels={l['id']:l for l in w.current_labels() if l['status']=='confirmed'};original=QFileDialog.getSaveFileName
            try:
                for ext in ['gpkg','shp','geojson']:
                    path=folder/('labels.'+ext);QFileDialog.getSaveFileName=lambda *a,p=path,**k:(str(p),f'{ext} (*.{ext})');w.export('gpkg');wait()
                    ds=ogr.Open(str(path));layer=ds.GetLayer(0);assert layer.GetFeatureCount()==len(labels)
                    inverse=~Affine(*image['transform']);a,b,c,d,e,f=list(inverse)[:6]
                    for feature in layer:
                        label=labels[feature.GetField('label_id')];g=json.loads(feature.GetGeometryRef().ExportToJson())
                        if ext=='geojson':g=transform_geom('EPSG:4326',image['crs'],g)
                        pixels=affine_transform(shape(g),[a,b,d,e,c,f]);assert pixels.hausdorff_distance(shape(label['geometry']))<1e-4 and feature.GetField('class_id')==1
                    ds=None
            finally:QFileDialog.getSaveFileName=original
        w.capture_workspace();w.save();w.autosave();wait()
        (OUT/'visual_review.json').write_text(json.dumps({'ok':True,'reviews':rows,'all_vectors_reverified':True},indent=2));print('Visual review complete',flush=True)
    finally:w.dirty=False;w.close();wait();w.close()

if __name__=='__main__':
    from multiprocessing import freeze_support
    freeze_support();main()
