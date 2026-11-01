"""Previous/next must follow the actual visible table, including filters."""
from shapely.geometry import box,mapping
from test_workbench import workbench,fake_image


def rows(window):return [row.identifier for row in window.label_presenter.rows]


def test_navigation_follows_numbered_rows_and_filtered_view(workbench):
    w,app,wait,errors=workbench
    image=fake_image('one');image['ready']=True;w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0)
    def label(identifier,status,x):
        return {'id':identifier,'image_id':'one','class_id':1,'status':status,'geometry':mapping(box(x,100,x+20,120)),
                'score':.9,'source':'interactive' if status=='confirmed' else 'automatic'}
    w.project['labels']=[label('saved-z','confirmed',900),label('saved-a','confirmed',100),
                         label('candidate-c','candidate',800),label('candidate-a','candidate',500),label('candidate-b','candidate',300)]
    w.refresh_labels();wait()
    assert rows(w)==['saved-z','saved-a','candidate-a','candidate-b','candidate-c']
    w.select_label('saved-z');w.review_target(1);assert w.selected_id=='saved-a'
    w.review_target(1);assert w.selected_id=='candidate-a'
    assert rows(w)==['saved-z','saved-a','candidate-a','candidate-b','candidate-c']
    w.review_target(1);assert w.selected_id=='candidate-b'
    w.review_target(-1);assert w.selected_id=='candidate-a'
    w.clear_draft();w.label_filter.setCurrentIndex(1);assert rows(w)==['saved-z','saved-a']
    w.select_label('saved-a');w.review_target(1);assert w.selected_id=='saved-z'
    w.clear_draft();w.label_filter.setCurrentIndex(2);assert rows(w)==['candidate-a','candidate-b','candidate-c']
    w.review_target(-1);assert w.selected_id=='candidate-c'
    w.review_target(1);assert w.selected_id=='candidate-a'
    w.auto_apply.setChecked(False);w.add_point(510,110,1);before=dict(w.draft);w.review_target(1);assert w.selected_id=='candidate-a' and w.draft==before
    assert not errors


def test_navigation_disabled_when_filter_has_no_rows(workbench):
    w,app,wait,errors=workbench
    image=fake_image('one');image['ready']=True;w.project['images']=[image]
    w.refresh_images();w.images.setCurrentRow(0)
    w.project['labels']=[{'id':'saved','image_id':'one','class_id':1,'status':'confirmed',
                          'geometry':mapping(box(10,10,20,20))}]
    w.refresh_labels();wait();w.label_filter.setCurrentIndex(2)
    assert not rows(w) and not w.previous_button.isEnabled() and not w.next_button.isEnabled()
    w.review_target(1);assert not w.draft
