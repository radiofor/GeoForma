import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QToolBar,QToolButton
from shapely.geometry import box,mapping
from geoforma.window import MainWindow


def test_panel_actions_replace_menus_and_duplicate_toolbar_entries():
    app=QApplication.instance() or QApplication([]);w=MainWindow(auto_prepare=False);w.autosave=lambda:None
    assert w.menuBar().isHidden() and not w.menuBar().actions()
    assert not hasattr(w,'more_button') and not hasattr(w,'options_menu')
    assert w.reprepare_button.text()=='重新准备全图' and not hasattr(w,'export_crs_button')
    assert not hasattr(w,'export_kind') and w.vector_export_button.text()=='导出标签'
    assert not hasattr(w,'undo_label_button') and not hasattr(w,'edit_button')
    assert all(a in w.actions() for a in w.project_actions.values())
    assert [w.project_actions[k].shortcut().toString() for k in ('new','open','save','recover')]==['','','','']
    assert 'save_as' not in w.project_actions and w.recover_button.text()=='恢复'
    assert all(action.shortcut().isEmpty() for action in [*w.mode_actions.values(),w.import_action,w.raw_view_action,w.fit_action,w.native_zoom_action])
    assert w.delete_action.shortcut().toString()=='Del'
    assert w.apply_button.shortcut().isEmpty() and w.confirm_button.shortcut().isEmpty()
    assert {key.toString() for key in w.save_label_shortcut.keys()}=={'Return','Enter'}
    assert [action.shortcut().toString() for action in (w.undo_prompt_action,w.redo_prompt_action,w.undo_label_action)]==['Ctrl+Z','Ctrl+Shift+Z','Ctrl+Alt+Z']
    assert w.new_target_button.shortcut().toString()=='Esc'
    tools=[a.text() for toolbar in w.findChildren(QToolBar) for a in toolbar.actions()]
    assert '导出' not in tools and '保存项目' not in tools and '保存' not in tools
    assert len([b for b in w.findChildren(QToolButton) if b.defaultAction() is w.project_actions['save']])==1
    export=[];w.export=lambda kind:export.append(kind)
    w.image={'id':'test','width':1000,'height':1000,'model_recipe':None};w.project['labels']=[{'id':'candidate','image_id':'test','status':'candidate','class_id':None,'geometry':mapping(box(0,0,1,1))}]
    w.refresh_labels();assert not w.vector_export_button.isEnabled()
    w.project['labels'][0].update(status='confirmed',class_id=1);w.refresh_labels()
    assert w.vector_export_button.isEnabled();w.vector_export_button.click();assert export==['gpkg']
    w.image=None;w.project['labels']=[];w.dirty=False;w.close();app.processEvents()
