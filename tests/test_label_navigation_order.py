"""Table order and manual selection follow the visible label records."""
from shapely.geometry import box,mapping
from test_workbench import workbench,fake_image


def rows(window):return [row.identifier for row in window.label_presenter.rows]


def test_selection_follows_numbered_rows(workbench):
    w,app,wait,errors=workbench
    image=fake_image('one');image['ready']=True;w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0)
    def label(identifier,status,x):
        return {'id':identifier,'image_id':'one','class_id':1,'status':status,'geometry':mapping(box(x,100,x+20,120)),
                'score':.9,'source':'interactive' if status=='confirmed' else 'automatic'}
    w.project['labels']=[label('saved-z','confirmed',900),label('saved-a','confirmed',100),
                         label('saved-b','confirmed',300),label('legacy','candidate',500)]
    w.refresh_labels();wait()
    assert rows(w)==['saved-z','saved-a','saved-b']
    w.select_label('saved-z');w.select_label('saved-a');assert w.selected_id=='saved-a'
    w.select_label('saved-b');assert w.selected_id=='saved-b'
    w.select_label('saved-z');assert w.selected_id=='saved-z'
    w.clear_draft();w.select_label('saved-z')
    w.select_label('saved-b');assert w.selected_id=='saved-b'
    w.select_label('saved-z');assert w.selected_id=='saved-z'
    w.select_label('saved-a')
    w.auto_apply.setChecked(False);w.add_point(510,110,1);before=dict(w.draft);selected=w.selected_id
    w.select_label('saved-b');assert w.draft==before
    assert not errors


def test_category_buttons_disabled_when_no_rows(workbench):
    w,app,wait,errors=workbench
    image=fake_image('one');image['ready']=True;w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0)
    w.project['labels']=[]
    w.refresh_labels();wait()
    assert not rows(w) and not w.category_buttons.isEnabled() and not w.draft
