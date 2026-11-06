"""A repaired reshape is committed as valid, non-overlapping labels."""
import copy
from shapely.geometry import Polygon,box,mapping,shape
from test_reshape import workbench,raster_image


def test_invalid_reshape_is_repaired_without_overwriting_another_label(workbench):
    w,app,_=workbench
    w.smooth_enabled.setChecked(False);w.single_polygon.setChecked(False)
    original=copy.deepcopy(w.project['labels'][0])
    blocker=dict(original,id='other',geometry=mapping(box(32,20,34,22)))
    w.project['labels'].append(blocker);w.refresh_labels()
    session={'label':original,'target':'auto','context':w.annotation_context(),'stroke':[],'alternate':False}
    w.reshape_session=session
    invalid=Polygon([(20,20),(36,30),(20,30),(36,20),(20,20)])
    assert not invalid.is_valid
    result={'geometry':mapping(invalid),'stroke':[[20,20],[36,30]],'alternate':False,
            'window':[20,20,16,10],'added_pixels':1,'removed_pixels':1}
    w.apply_reshape_results(session,[('label',original)],[result])
    labels=[label for label in w.project['labels'] if label['id']!='other']
    assert len(labels)>=2 and all(shape(label['geometry']).is_valid for label in labels)
    assert all(shape(label['geometry']).intersection(shape(blocker['geometry'])).area==0 for label in labels)
    assert next(label for label in w.project['labels'] if label['id']=='other')==blocker
    w.undo_label();assert w.project['labels']==[original,blocker]
