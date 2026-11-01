import copy,json,os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QDialog
from geoforma.domain import new_project
from geoforma.model_preferences import application_settings,last_model,remember_model,LAST_MODEL_KEY
from geoforma.window import MainWindow


def config(family='sam',variant='vit_h',device='cpu',path='custom_weights.pth'):
    return dict(backend=family,variant=variant,device=device,execution='auto',checkpoint=path)


def window():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False)
    w.autosave=lambda:None;return w,app


def close(w,app):
    w.dirty=False;w.close();app.processEvents()


def test_first_use_recommends_sam21_small_without_loading_model():
    model=new_project()['model']
    assert model['backend']=='sam2.1' and model['variant']=='small' and model['device']=='cuda'
    assert model['checkpoint'].endswith('sam2.1_hiera_small.pt')
    w,app=window();assert w.project['model']==model and w.service.process is None
    close(w,app)


def test_preferences_restore_family_variant_device_path_and_auto_runtime(tmp_path):
    value=config('sam2','large','cpu',str(tmp_path/'model with spaces.pt'));value['execution']='wsl'
    assert remember_model(application_settings(),value)
    restored=last_model(application_settings())
    assert restored==dict(value,execution='auto')
    assert not (tmp_path/'model with spaces.pt').exists()


def test_closing_and_creating_new_window_restores_last_model():
    w,app=window();chosen=config();w.project['model']=copy.deepcopy(chosen);close(w,app)
    w,app=window();assert w.project['model']==chosen
    w.new();assert w.project['model']==chosen and not w.project['labels']
    close(w,app)


def test_project_model_has_priority_over_last_application_model(tmp_path):
    from geoforma.storage import save_project
    assert remember_model(application_settings(),config('sam2.1','large'))
    project=new_project(config('sam','vit_b'));path=tmp_path/'existing.geoforma.json';save_project(project,path)
    w,app=window();assert w.project['model']['variant']=='large'
    w.open_project(path);assert w.project['model']==project['model']
    close(w,app);assert last_model(application_settings())==project['model']


def test_confirming_model_persists_selection_even_before_download(monkeypatch,tmp_path):
    w,app=window();chosen=config('sam2.1','base_plus','cuda',str(tmp_path/'missing.pt'))
    class Dialog(QDialog):
        def __init__(self,config,parent):super().__init__(parent)
        def exec(self):return True
        def value(self):return dict(chosen)
    monkeypatch.setattr('geoforma.controllers.models.ModelDialog',Dialog)
    queued=[];w.run=lambda title,work,done,**kw:queued.append((work,done))
    w.configure_model();assert not queued and last_model(application_settings())==chosen
    close(w,app)


def test_invalid_or_unavailable_preferences_use_recommended_default():
    settings=application_settings()
    for raw in ('broken JSON',json.dumps({'backend':'sam3','variant':'large'}),json.dumps({'variant':'vit_b','device':'invalid'})):
        settings.setValue(LAST_MODEL_KEY,raw);settings.sync()
        assert last_model(settings)==new_project()['model']


def test_startup_worker_uses_last_model_without_loading_weights():
    from geoforma.startup import StartupWorker
    chosen=config('sam2.1','tiny','cpu');remember_model(application_settings(),chosen)
    app=QApplication.instance() or QApplication([]);worker=StartupWorker();worker.start()
    end=time.monotonic()+5
    while worker.isRunning() and time.monotonic()<end:app.processEvents();time.sleep(.002)
    assert not worker.isRunning() and not worker.error and worker.result.project['model']==chosen
