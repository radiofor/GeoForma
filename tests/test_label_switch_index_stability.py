"""A completed display index must not rebuild or restart the label list."""
import threading
import time

from shapely.geometry import box,mapping
from test_workbench import workbench,fake_image


def test_async_index_completion_does_not_rebuild_or_restart_label_list(workbench,monkeypatch):
    from geoforma.controllers import label_list

    w,app,wait,errors=workbench
    first,second=fake_image('first'),fake_image('second')
    w.project['images']=[first,second]
    w.project['labels']=[
        dict(id=f'{image["id"]}-{i}',image_id=image['id'],class_id=1,status='confirmed',
             geometry=mapping(box(i*3,0,i*3+2,2)))
        for image,count in ((first,1),(second,36)) for i in range(count)
    ]
    w.refresh_images();w.images.setCurrentRow(0);wait()

    started=threading.Event();release=threading.Event();original=label_list.LabelIndex
    def blocked(labels,task=None):
        if labels and labels[0]['image_id']=='second':
            started.set()
            if not release.wait(5):raise TimeoutError('合成索引未释放')
        return original(labels,task)
    monkeypatch.setattr(label_list,'LabelIndex',blocked)
    reveals=[];transition=w.label_presenter.transition;reveal=transition.reveal
    def track_reveal(*args,**kwargs):
        reveals.append(args)
        return reveal(*args,**kwargs)
    monkeypatch.setattr(transition,'reveal',track_reveal)
    try:
        w.images.setCurrentRow(1)
        deadline=time.monotonic()+5
        while not started.is_set() and time.monotonic()<deadline:
            app.processEvents();time.sleep(.002)
        assert started.is_set() and w.labels_table.rowCount()==36
        assert len(reveals)==1
        changes=[];model=w.labels_table.model()
        for signal in (model.dataChanged,model.rowsInserted,model.rowsRemoved,model.modelReset,model.layoutChanged):
            signal.connect(lambda *args:changes.append(args))
        release.set()
        while w.label_index_task is not None and time.monotonic()<deadline:
            app.processEvents();time.sleep(.002)
        assert w.label_index_task is None and w.label_index_key[0]=='second'
        assert not changes and len(reveals)==1 and not errors
    finally:
        release.set()
