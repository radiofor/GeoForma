import json,pytest


def test_malformed_history_is_rejected(tmp_path):
    from geoforma.domain import new_project
    from geoforma.storage import load_project
    project=new_project();project['history']={'schema':1,'labels':{'individual':{'undo':['invalid'],'redo':[]}}}
    path=tmp_path/'invalid.gfm';path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError,match='历史'):
        load_project(path)
