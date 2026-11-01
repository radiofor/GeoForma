import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.window import MainWindow


def test_local_apply_accepts_new_objects_and_legacy_labels():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    w.image={'id':'test','width':1000,'height':1000,'ready':True,'model_recipe':None}
    w.refresh_labels=lambda:w.update_controls()
    w.auto_apply.setChecked(False);w.add_point(120,120,1)
    assert w.mode_index==0 and w.apply_button.isEnabled() and not hasattr(w,'auto_button')
    candidate=dict(id='candidate',image_id='test',status='candidate',annotation_mode='automatic',geometry=mapping(box(100,100,200,200)))
    w.project['labels']=[candidate];w.update_controls()
    assert w.apply_button.isEnabled()
    w.draft['base_id']='candidate';w.update_controls();assert w.apply_button.isEnabled()
    candidate['status']='confirmed';w.update_controls();assert w.apply_button.isEnabled()
    w.project['labels']=[];w.update_controls();assert w.apply_button.isEnabled()
    w.draft={};w.add_point(120,120,1)
    assert w.apply_button.isEnabled() and w.draft['points']==[[120,120,1]]
    w.dirty=False;w.close();app.processEvents()
