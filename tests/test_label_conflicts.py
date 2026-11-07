import copy,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from shapely.geometry import box,mapping,shape
from geoforma.label_conflicts import conflicts,resolve,assert_no_overlaps


def label(identifier,g,category=1,image='image',status='confirmed'):
    return {'id':identifier,'geometry':mapping(g),'image_id':image,'status':status,'class_id':category}


def test_touching_edges_other_images_and_candidates_are_not_conflicts():
    a=label('a',box(0,0,10,10));others=[label('b',box(10,0,20,10)),label('c',box(0,0,10,10),image='other'),label('d',box(0,0,10,10),status='candidate')]
    assert not conflicts(a,others);assert_no_overlaps([a,*others])


def test_clip_preserves_existing_and_tiny_regions_and_holes():
    old=label('old',box(2,2,8,8));new=label('new',box(0,0,10,10));original=copy.deepcopy(old)
    result=resolve(new,[old]);g=shape(result['geometry'])
    assert len(g.interiors)==1 and g.area==64 and old==original
    assert not result['removed'];assert_no_overlaps([old,dict(new,geometry=result['geometry'])])
    tiny=resolve(label('t',box(0,0,1,1)),[label('o',box(0,0,.999,1))])
    assert shape(tiny['geometry']).area==pytest.approx(.001)


def test_full_coverage_returns_empty_without_mutation_and_edit_excludes_itself():
    old=label('old',box(0,0,10,10));new=label('new',box(1,1,2,2))
    assert resolve(new,[old])['geometry'] is None
    assert not conflicts(old,[old]) and shape(resolve(old,[old])['geometry']).area==100


def test_merge_connected_same_class_chain_clips_other_classes():
    peers=[label('a',box(0,0,10,10)),label('b',box(9,0,20,10)),label('c',box(15,0,25,5),2)]
    new=label('new',box(-1,0,1,10));original=copy.deepcopy(peers)
    result=resolve(new,peers,'merge');assert {l['id'] for l in result['removed']}=={'a','b'}
    assert shape(result['geometry']).area==185 and peers==original
    assert_no_overlaps([peers[2],dict(new,geometry=result['geometry'])])


def test_old_overlaps_rejected_but_candidate_export_allowed():
    peers=[label('a',box(0,0,10,10)),label('b',box(9,0,20,10))]
    with pytest.raises(ValueError,match='存在重叠'):assert_no_overlaps(peers)
    assert_no_overlaps([dict(l,status='candidate') for l in peers])


def test_ui_automatic_clip_is_atomic_and_undoable(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from geoforma.window import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    old=label('old',box(0,0,10,10));w.project['labels']=[old];original=copy.deepcopy(w.project['labels'])
    w.draft={'geometry':mapping(box(5,0,15,10)),'points':[],'pending':False}
    w.confirm()
    assert len(w.project['labels'])==2 and w.project['labels'][0]==old
    assert shape(w.project['labels'][1]['geometry']).area==50
    assert w.project['labels'][1]['model']['overlap_resolution']['component_policy']=='largest_area'
    w.undo_label();assert w.project['labels']==original
    w.redo_label();assert len(w.project['labels'])==2 and shape(w.project['labels'][1]['geometry']).area==50
    assert_no_overlaps(w.project['labels'])
    w.dirty=False;w.close();app.processEvents()


def test_fully_covered_label_reports_nonmodal_failure():
    from PySide6.QtWidgets import QApplication
    from geoforma.window import MainWindow
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'image','width':1000,'height':1000,'ready':True,'model_recipe':None,'display_recipe':None}
    w.project['labels']=[label('old',box(0,0,10,10))];before=copy.deepcopy(w.project['labels'])
    w.draft={'geometry':mapping(box(1,1,2,2)),'points':[],'pending':False};w.confirm()
    assert w.project['labels']==before and w.draft['geometry']
    assert '轮廓被已有标签完全占用' in w.statusBar()._error_toast.label.text()
    w.dirty=False;w.close();app.processEvents()
