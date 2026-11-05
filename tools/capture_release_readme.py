"""Capture real current Qt widgets with isolated, explicitly synthetic GIS data."""
import argparse,json,os,shutil,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);args=parser.parse_args()
    out=args.output.resolve();data=args.data.resolve();out.mkdir(parents=True,exist_ok=True);data.mkdir(parents=True,exist_ok=True)
    os.environ.update(QT_QPA_PLATFORM='offscreen',GEOFORMA_DATA_DIR=str(data/'resources'),GEOFORMA_SETTINGS_FILE=str(data/'settings.ini'))
    from main import configure_runtime
    configure_runtime()
    import numpy as np,rasterio
    from rasterio.transform import from_origin
    from rasterio.features import rasterize
    from shapely.geometry import Polygon,mapping
    from PySide6.QtWidgets import QApplication
    from geoforma.raster import inspect_source,make_recipe
    from geoforma.window import MainWindow
    from geoforma import native_runtime
    from geoforma.ui.resources import ResourceDialog
    from geoforma.distribution import VERSION
    # Same optional-runtime branch selected by the frozen build's marker.
    native_runtime.lightweight=lambda:True
    shapes=[Polygon([(180,155),(205,125),(247,130),(280,155),(270,205),(235,230),(190,215)]),
            Polygon([(520,270),(548,250),(580,273),(592,322),(565,345),(532,323)]),
            Polygon([(315,485),(330,455),(360,440),(400,462),(410,505),(375,535),(333,520)])]
    yy,xx=np.mgrid[:720,:960];terrain=20*np.sin(xx/58)+16*np.cos(yy/42)+9*np.sin((xx+yy)/27)
    pixels=np.stack([142+terrain,132+terrain,106+terrain]).clip(0,255).astype('uint8')
    mask=rasterize([(mapping(g),1) for g in shapes],out_shape=(720,960)).astype(bool)
    pixels[:,mask]=np.array([38,142,149],dtype='uint8')[:,None]
    source=data/'demo.tif'
    with rasterio.open(source,'w',driver='GTiff',width=960,height=720,count=3,dtype='uint8',crs='EPSG:32645',transform=from_origin(500000,3000000,2,2)) as ds:ds.write(pixels)
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.autosave=lambda:None;w.autosave_timer.stop();w.auto_apply.setChecked(False)
    w.project['classes']=[{'id':1,'name':'湖泊'},{'id':2,'name':'其他水体'}];w.project['next_class_id']=3;w.refresh_classes()
    image=inspect_source(source);image['model_recipe']=make_recipe(image,[1,2,3]);image['display_recipe']=image['model_recipe'];image['ready']=False
    images=[image]
    for number in (2,3):
        other=data/f'demo_{number}.tif';shutil.copy2(source,other)
        record=inspect_source(other);record['review_complete']=number==2;images.append(record)
    w.project['images']=images
    w.project['references']=[dict(image,group=name,fingerprint='synthetic-'+name) for name in ('NDWI','VV-DESC','VV-ASC')]
    w.refresh_images();w.images.setCurrentRow(0)
    w.project_path=data/'demo.gfm';w.refresh_project_title();w.update_controls();w.resize(1440,960);w.show()
    def settle():
        deadline=time.monotonic()+20
        while True:
            app.processEvents();time.sleep(.02)
            busy=w.render_task or w.render_timer.isActive() or w.smoother.task or w.smoother.timer.isActive() or w.label_index_task
            if not busy:break
            if time.monotonic()>deadline:raise TimeoutError('Screenshot render did not settle')
        for _ in range(5):app.processEvents()
    def shot(filename):settle();assert w.grab().save(str(out/filename))
    settle();w.view.fit_image();shot('step2-image.png')
    for geometry in shapes[:2]:
        w.set_tool('draw_polygon')
        for x,y in list(geometry.exterior.coords)[:-1]:w.add_manual_vertex(x,y)
        w.finish_manual_polygon();w.confirm()
    combo=w.labels_table.category_combo(1);combo.setCurrentIndex(combo.findData(2))
    w.set_tool('draw_polygon')
    for x,y in list(shapes[2].exterior.coords)[:-1]:w.add_manual_vertex(x,y)
    w.finish_manual_polygon();shot('step3-label.png')
    assert any(r.status=='未保存' for r in w.label_presenter.rows)
    shot('main-window.png')
    w.confirm();w.set_tool('select');w.select_label(w.project['labels'][-1]['id']);shot('step4-export.png')
    w.view.setFocus()
    w.begin_reshape(auto=True)
    for point in ((190,150),(185,240),(245,250),(245,200)):w.add_reshape_point(*point)
    shot('step3-reshape.png');w.cancel_reshape()
    # Capture the actual class dropdown and multi-target editing controls.
    w.labels_table.category_combo(1).showPopup();app.processEvents();w.labels_table.category_combo(1).hidePopup()
    dialog=ResourceDialog(w);dialog.show();app.processEvents()
    dialog.tabs.setCurrentIndex(0);app.processEvents();assert dialog.grab().save(str(out/'step1-runtime.png'))
    assert dialog.grab().save(str(out/'resource-settings.png'))
    dialog.tabs.setCurrentIndex(1);app.processEvents();assert dialog.grab().save(str(out/'step1-weights.png'))
    dialog.close()
    from geoforma.dialogs import ClassesDialog
    demo_classes=[dict(w.project['classes'][0],name='高山冰川湖泊与周边季节性积水区域（长期监测、边界复核及变化记录）'),w.project['classes'][1]]
    classes=ClassesDialog(demo_classes,w.project['next_class_id'],set(),1,w)
    classes.resize(480,400);classes.show();classes.expand_name_button.click();app.processEvents()
    assert classes.grab().save(str(out/'step5-classes.png'));classes.close()
    w.image=None;w.dirty=False;w.close();app.processEvents()
    (data/'screenshots.json').write_text(json.dumps({'version':VERSION,'synthetic_data':True,'inference_claimed':False,'screenshots':[p.name for p in out.glob('*.png')],'ok':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Captured current Qt screenshots for',VERSION,flush=True)


if __name__=='__main__':main()
