"""Automatic model loading starts after imagery is available."""
from geoforma.workflow import preparation_signature
from test_workbench import workbench, fake_image


def test_empty_workbench_keeps_project_actions_available(workbench, monkeypatch):
    w, app, wait, errors = workbench
    calls = []
    monkeypatch.setattr(w.service, 'prepare_model', lambda *args: calls.append(args))
    w.project_path = None
    monkeypatch.setattr(w, 'previous_work', lambda: 'previous.gfm')
    w.update_controls()
    w.auto_prepare = True
    w.remind_resources(); w.pump_preparation(); app.processEvents()
    assert not calls and w.task is None and not errors
    assert w.project_actions['new'].isEnabled() and w.project_actions['open'].isEnabled()
    assert w.project_actions['recover'].isEnabled()


def test_prepared_image_loads_the_model(workbench, monkeypatch):
    w, app, wait, errors = workbench
    calls = []
    monkeypatch.setattr(w.service, 'activate_project', lambda *args: False)
    def prepare(config, task):
        calls.append(config)
        return dict(checkpoint=config['checkpoint'], device='cpu', execution='native')
    monkeypatch.setattr(w.service, 'prepare_model', prepare)
    image = fake_image('image'); image['ready'] = True
    image['prepared_full_signature'] = preparation_signature(image, w.project['model'])
    w.project['images'] = [image]; w.image = image
    w.auto_prepare = True; w.queue_preparation(); wait()
    assert len(calls) == 1 and w.runtime_status and not errors
