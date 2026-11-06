"""Clipping must not transfer a draft component's identity or class."""
import pytest
from shapely.geometry import MultiPolygon,box,mapping,shape
from test_workbench import workbench,fake_image


@pytest.mark.parametrize('cut', [8, 10])
def test_confirm_preserves_component_class_after_overlap(workbench,cut):
    w,app,wait,errors=workbench
    image=fake_image('image');w.project['images']=[image]
    w.project['classes'].append({'id':2,'name':'类别 2'});w.refresh_classes()
    blocker={'id':'blocker','image_id':'image','class_id':1,'status':'confirmed',
             'geometry':mapping(box(0,0,cut,10))}
    w.project['labels']=[blocker];w.refresh_images();w.images.setCurrentRow(0)
    w.single_polygon.setChecked(False)
    w.draft={'geometry':mapping(MultiPolygon([box(0,0,10,10),box(20,0,26,6)])),
             'class_id':1,'display_ids':['large','small'],'part_classes':{'large':1,'small':2}}
    w.refresh_labels();w.confirm();wait()
    saved={item['id']:item for item in w.project['labels'] if item['id']!='blocker'}
    assert saved['small']['class_id']==2 and shape(saved['small']['geometry']).equals(box(20,0,26,6))
    if cut==8:
        assert saved['large']['class_id']==1 and shape(saved['large']['geometry']).equals(box(8,0,10,10))
    else:assert 'large' not in saved
    w.undo_label();wait();assert w.project['labels']==[blocker]
    w.redo_label();wait();assert {item['id'] for item in w.project['labels']}=={'blocker',*saved}
    assert not errors


def test_resolved_component_split_inherits_class_with_fresh_identity():
    from geoforma.label_parts import split_resolved_label
    original=mapping(box(0,0,10,10))
    resolved=mapping(MultiPolygon([box(0,0,4,10),box(6,0,10,10)]))
    parts=split_resolved_label({'id':'source','geometry':resolved,'class_id':1},original,['source'],{'source':2})
    assert len(parts)==2 and parts[0]['id']=='source' and parts[1]['id']!='source'
    assert {part['class_id'] for part in parts}=={2}


def test_batch_confirm_removes_replaced_base_when_its_first_component_is_clipped(workbench):
    w,app,wait,errors=workbench
    image=fake_image('image');w.project['images']=[image]
    w.project['classes'].append({'id':2,'name':'类别 2'});w.refresh_classes()
    blocker={'id':'blocker','image_id':'image','class_id':1,'status':'confirmed','geometry':mapping(box(0,0,10,10))}
    old={'id':'old','image_id':'image','class_id':1,'status':'confirmed','geometry':mapping(box(40,0,45,5))}
    w.project['labels']=[blocker,old];w.refresh_images();w.images.setCurrentRow(0)
    first={'base_id':'old','geometry':mapping(MultiPolygon([box(0,0,10,10),box(20,0,26,6)])),
           'class_id':1,'display_ids':['old','small'],'part_classes':{'small':2}}
    second={'geometry':mapping(box(60,0,65,5)),'class_id':1,'display_ids':['new']}
    w.draft={'reshape_batch':[first,second]};w.confirm_reshape_batch();wait()
    saved={item['id']:item for item in w.project['labels']}
    assert set(saved)=={'blocker','small','new'} and saved['small']['class_id']==2
    w.undo_label();wait();assert w.project['labels']==[blocker,old]
    w.redo_label();wait();assert {item['id'] for item in w.project['labels']}=={'blocker','small','new'}
    assert not errors


def test_component_failure_keeps_draft_and_saved_labels(workbench,monkeypatch):
    from geoforma import label_parts
    w,app,wait,errors=workbench
    image=fake_image('image');w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0)
    w.draft={'geometry':mapping(box(0,0,10,10)),'class_id':1,'display_ids':['draft']}
    def fail(*args,**kwargs):raise ValueError('合成几何错误')
    monkeypatch.setattr(label_parts,'split_resolved_label',fail)
    w.confirm()
    assert not w.project['labels'] and w.draft['display_ids']==['draft'] and errors==['合成几何错误']
