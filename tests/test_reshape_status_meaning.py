"""A reshape session is not a request to undo a manual edit."""
import copy

from test_reshape import workbench,raster_image


def test_reshape_session_does_not_claim_manual_edits_must_be_undone(workbench):
    w,app,_=workbench
    original=copy.deepcopy(w.project['labels'])
    w.begin_reshape(auto=True)
    w.update_draft_info()
    assert '撤回' not in w.edit_status.text() and '取消编辑后新建' not in w.edit_status.text()
    assert w.project['labels']==original


def test_manual_prompt_restriction_explains_cancel_not_undo(workbench):
    from geoforma.editing_state import require_model_editable
    from geoforma.ui.text import ui_text
    import pytest
    message=ui_text('reshape.locked')
    assert '撤回' not in message and '取消编辑' in message
    with pytest.raises(ValueError,match=message):require_model_editable({'editing_state':'manual'})
