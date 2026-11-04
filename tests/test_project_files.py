"""Project file suffixes stay independent of the JSON storage format."""
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog,QMessageBox

from geoforma.project_files import new_project_path,project_name
from geoforma.storage import load_project,save_project
from test_project_autosave import automatic_project,until


@pytest.mark.parametrize('name,expected',[
    ('lake','lake.gfm'),('lake.v2','lake.v2.gfm'),('lake.gfm','lake.gfm'),
    ('LAKE.GFM','LAKE.GFM'),('lake.json','lake.json.gfm'),
])
def test_project_filename_and_display_name(tmp_path,name,expected):
    result=new_project_path(tmp_path/name)
    assert result.name==expected
    assert project_name(result)==expected[:-4]


def test_first_save_uses_gfm_and_autosaves_same_file(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;dialog=[]
    def choose(*args):dialog.append(args);return str(tmp/'lake'),''
    monkeypatch.setattr(QFileDialog,'getSaveFileName',choose)
    w.save();path=tmp/'lake.gfm'
    assert w.project_path==path and w.project_title.text()=='lake'
    assert dialog[0][2].endswith('project.gfm') and '*.gfm' in dialog[0][3]
    assert json.loads(path.read_text(encoding='utf-8'))['name']=='lake'
    w.project['classes'][0]['name']='修改后';w.mark_dirty();w.autosave()
    until(app,lambda:not w.dirty and w.autosave_task is None)
    assert load_project(path)['classes'][0]['name']=='修改后'
    assert w.settings.value('recovery/last_work')==str(path)
    assert not list(tmp.glob('lake*.json'))


def test_normalized_path_does_not_overwrite_without_confirmation(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;target=tmp/'lake.gfm';target.write_bytes(b'existing')
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(tmp/'lake'),''))
    asked=[]
    monkeypatch.setattr(QMessageBox,'question',lambda *args:(asked.append(args) or QMessageBox.StandardButton.No))
    w.save();assert len(asked)==1 and target.read_bytes()==b'existing' and w.project_path is None


def test_open_dialog_accepts_gfm_projects(automatic_project,monkeypatch):
    w,app,tmp=automatic_project;path=tmp/'new.gfm';save_project(w.project,path);calls=[];dialogs=[]
    def choose(*args):dialogs.append(args);return str(path),''
    monkeypatch.setattr(QFileDialog,'getOpenFileName',choose)
    monkeypatch.setattr(w,'request_project_open',lambda value:calls.append(Path(value)))
    w.open_dialog()
    assert calls==[path] and '*.gfm' in dialogs[0][3] and '*.json' not in dialogs[0][3]
    assert load_project(path)['cache_id']==w.project['cache_id']


@pytest.mark.parametrize('name',['old.geoforma.json','old.json'])
def test_old_project_suffix_is_rejected_for_load_save_and_recovery(automatic_project,name):
    w,app,tmp=automatic_project;path=tmp/name
    path.write_text(json.dumps(w.project),encoding='utf-8');before=path.read_bytes()
    with pytest.raises(ValueError,match=r'\.gfm'):load_project(path)
    with pytest.raises(ValueError,match=r'\.gfm'):save_project(w.project,path)
    w.settings.setValue('recovery/last_work',str(path))
    assert w.previous_work() is None and path.read_bytes()==before
