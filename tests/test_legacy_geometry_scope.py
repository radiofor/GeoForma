"""Legacy contour rejection is consistent and limited to annotation records."""
import copy
import json

import pytest

from geoforma.domain import new_project
from geoforma.project_validation import validate_project
from geoforma.storage import load_project,save_project
from test_reshape import raster_image


def test_metadata_with_same_field_names_round_trips(tmp_path):
    project=new_project()
    project['model']['source_geometry']='model metadata'
    project['description']={'raw_geometry':'not a label'}
    path=tmp_path/'project.gfm'
    save_project(project,path)
    restored=load_project(path)
    assert restored['model']['source_geometry']=='model metadata'
    assert restored['description']==project['description']


@pytest.mark.parametrize('location',['workspace','image','session','prompt_history','prompt_label_history','label_history'])
def test_legacy_fields_in_drafts_and_history_rejected_on_read_and_write(tmp_path,raster_image,location):
    project=new_project();image=copy.deepcopy(raster_image);project['images']=[image]
    draft={'raw_geometry':{'type':'Polygon','coordinates':[]}}
    if location=='workspace':project['workspace']['draft']=draft
    elif location=='image':image['working_draft']=draft
    elif location=='session':image['mode_sessions']={'individual':{'draft':draft}}
    elif location=='prompt_history':image['mode_sessions']={'individual':{'undo':[{'_draft':draft}]}}
    elif location=='prompt_label_history':
        old={'id':'test','image_id':image['id'],'source_geometry':{}}
        image['mode_sessions']={'individual':{'undo':[{'_draft':{},'_label_entries':[['test',old,0]]}]}}
    else:
        old={'id':'test','image_id':image['id'],'source_geometry':{}}
        project['history']={'schema':1,'labels':{'individual':{'undo':[[['test',old,0]]],'redo':[]}}}
    path=tmp_path/'project.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='旧轮廓字段'):validate_project(project)
    with pytest.raises(ValueError,match='旧轮廓字段'):load_project(path)
    with pytest.raises(ValueError,match='旧轮廓字段'):save_project(project,path)
    assert path.read_bytes()==before
