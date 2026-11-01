"""Create a local demonstration project. All imported regions remain unconfirmed."""
import sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from osgeo import ogr
from rasterio.transform import Affine
from shapely.geometry import shape,mapping
from shapely.affinity import affine_transform
from geoforma.storage import load_project,save_project
from geoforma.domain import prompt_window


def main():
    ogr.UseExceptions();project=load_project(ROOT/'experiments/desktop/smoke.geoforma.json');project['name']='Himalaya demo'
    for label in project['labels']:
        label['status']='candidate';label['class_id']=None;label['source']='software_test_draft';label.pop('confirmed_at',None)
    for provider,image in zip(['low','high'],project['images']):
        inverse=~Affine(*image['transform']);a,b,c,d,e,f=list(inverse)[:6]
        ds=ogr.Open(str(ROOT/f'experiments/lake_review/{provider}/lake_only_draft.gpkg'));layer=ds.GetLayerByName('lake_drafts')
        for feature in layer:
            geometry=affine_transform(shape(json.loads(feature.GetGeometryRef().ExportToJson())),[a,b,d,e,c,f]);center=geometry.representative_point()
            project['labels'].append({'id':f"review_{provider}_{feature.GetField('lake_id')}",'image_id':image['id'],'status':'candidate','class_id':None,
                'geometry':mapping(geometry),'source':'ai_reviewed_draft','window':list(prompt_window([[center.x,center.y,1]])),
                'points':[],'box':None,'edge':False,'score':None,'model':copy.deepcopy(project['model'])})
        ds=None
    target=next(l for l in project['labels'] if l['id']=='review_high_L28')
    project['workspace']={'image_id':project['images'][1]['id'],'class_id':1,'scope':'view','view_window':[3100,3900,750,750],
        'draft':{'base_id':target['id'],'geometry':copy.deepcopy(target['geometry']),'window':target['window'],'points':[],'box':None,'edge':False}}
    path=ROOT/'examples/himalaya.geoforma.json';save_project(project,path);print(str(path),len(project['labels']),'unconfirmed regions')


if __name__=='__main__':main()
