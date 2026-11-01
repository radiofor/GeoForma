import copy
import json
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QColorDialog,QLineEdit,QSpinBox
from PySide6.QtTest import QTest
from shapely.geometry import box,mapping
from geoforma.class_colors import class_color,default_color,allocate_color,HIGHLIGHTS,PALETTE
from geoforma.classes import validate_classes
from geoforma.dialogs import ClassesDialog
from geoforma.storage import save_project,load_project,project_snapshot
from geoforma.domain import new_project
from geoforma.theme import SELECTION,EDITING
from test_workbench import workbench,fake_image


def test_automatic_colors_are_distinct_stable_and_avoid_highlights():
    categories=[]
    for identifier in range(1,25):
        categories.append(dict(id=identifier,name=str(identifier),color=allocate_color(identifier,categories)))
    colors=[class_color(category) for category in categories]
    assert colors[:8]==list(PALETTE)
    assert len(set(colors))==24 and not set(colors)&{color.upper() for color in HIGHLIGHTS}
    assert [class_color(category) for category in reversed(categories)]==colors[::-1]
    assert all(color==color.upper() for color in colors)
    assert default_color(1)=='#EF3340' and len({default_color(i) for i in range(1,100)})==99
    assert allocate_color(2,[dict(id=1,name='custom',color=default_color(2))])!=default_color(2)


def test_exhausted_palette_has_a_bounded_unique_fallback(monkeypatch):
    import geoforma.class_colors as colors
    categories=[dict(id=i+1,name=str(i),color=color) for i,color in enumerate(PALETTE)]
    monkeypatch.setattr(colors,'default_color',lambda identifier:PALETTE[0])
    allocated=allocate_color(99,categories)
    assert allocated not in set(PALETTE)|{color.upper() for color in HIGHLIGHTS} and len(allocated)==7


@pytest.mark.parametrize('value',['red','#fff','#12345678','123456','#xyzxyz',None])
def test_invalid_color_is_rejected_by_category_and_project_validation(tmp_path,value):
    category=dict(id=1,name='湖泊',color=value)
    with pytest.raises(ValueError,match='颜色'):validate_classes([category])
    project=new_project();project['classes']=[category];path=tmp_path/'invalid.geoforma.json'
    with pytest.raises(ValueError,match='颜色'):save_project(project,path)
    path.write_text(json.dumps(project),encoding='utf-8')
    with pytest.raises(ValueError,match='颜色'):load_project(path)


def test_color_swatch_click_updates_only_staged_category_and_keeps_cancel_safe(monkeypatch):
    app=QApplication.instance() or QApplication([]);source=[dict(id=1,name='湖泊'),dict(id=2,name='道路')]
    dialog=ClassesDialog(source,3,{1},1);dialog.show();app.processEvents();before=copy.deepcopy(source)
    calls=[]
    monkeypatch.setattr('geoforma.ui.color_controls.choose_color',lambda color,name,parent:(calls.append((color,name)) or '#12AB34'))
    QTest.mouseClick(dialog.swatches[2],Qt.MouseButton.LeftButton)
    assert dialog.list.currentRow()==1 and dialog.name.text()=='道路'
    assert dialog.classes[1]['color']=='#12AB34' and dialog.swatches[2].color.name()=='#12ab34'
    assert calls==[(default_color(2),'道路')] and source==before
    monkeypatch.setattr('geoforma.ui.color_controls.choose_color',lambda *args:None)
    QTest.mouseClick(dialog.swatches[1],Qt.MouseButton.LeftButton)
    assert dialog.classes[0]==before[0] and not dialog.delete_button.isEnabled()
    dialog.reject();assert source==before


def test_clicking_category_text_still_selects_the_row():
    app=QApplication.instance() or QApplication([]);dialog=ClassesDialog([dict(id=1,name='湖泊'),dict(id=2,name='道路')],3,set(),1)
    dialog.show();app.processEvents()
    row=dialog.list.itemWidget(dialog.list.item(1));QTest.mouseClick(row,Qt.MouseButton.LeftButton,pos=row.rect().center())
    assert dialog.list.currentRow()==1 and dialog.name.text()=='道路'
    dialog.close()


def test_picker_supports_hex_and_rgb_with_no_alpha(monkeypatch):
    from geoforma.ui.color_controls import choose_color
    app=QApplication.instance() or QApplication([])
    def edit(dialog):
        assert dialog.testOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        assert not dialog.testOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
        hex_field=next(field for field in dialog.findChildren(QLineEdit) if field.text().lower()=='#0c2238')
        assert hex_field.text()=='#0C2238'
        hex_field.setFocus();hex_field.selectAll();QTest.keyClicks(hex_field,'#ab3456');app.processEvents()
        assert dialog.currentColor().name()=='#ab3456' and hex_field.text()=='#AB3456'
        red=dialog.findChildren(QSpinBox)[3]  # HSV occupies the first three fields.
        assert red.value()==171
        red.setValue(200);assert dialog.currentColor().red()==200
        assert hex_field.text()=='#C83456'
        dialog.accept();return 1
    monkeypatch.setattr(QColorDialog,'exec',edit)
    assert choose_color('#0c2238','湖泊')=='#C83456'


def test_colors_survive_rename_snapshot_and_project_reopen(tmp_path):
    app=QApplication.instance() or QApplication([]);project=new_project();project['classes'][0]['color']='#12ab34'
    dialog=ClassesDialog(project['classes'],2,set(),1);dialog.name.setText('湖泊');dialog.rename()
    assert dialog.classes[0]['color']=='#12ab34'
    project['classes']=dialog.classes;snapshot=project_snapshot(project);project['classes'][0]['color']='#345678'
    path=tmp_path/'colors.geoforma.json';save_project(snapshot,path)
    assert snapshot['classes'][0]['color']=='#12ab34'
    assert json.loads(path.read_text(encoding='utf-8'))['classes'][0]['color']=='#12AB34'
    assert load_project(path)['classes']==[dict(id=1,name='湖泊',color='#12AB34')]
    dialog.close()


def test_category_color_restyles_retained_contours_and_keeps_edit_highlights(workbench):
    w,app,wait,errors=workbench;image=fake_image('image');w.project['images']=[image];w.image=image
    w.project['classes']=[dict(id=1,name='湖泊',color='#12ab34'),dict(id=2,name='道路',color='#654321')]
    w.project['labels']=[dict(id=str(i),image_id='image',class_id=i%2+1,status='confirmed',annotation_mode='individual',geometry=mapping(box(i*40,0,i*40+20,20))) for i in range(3)]
    w.refresh_classes();w.refresh_labels();wait();items=dict(w.view.overlay_records);paths={key:item.path() for key,item in items.items()}
    assert [items[str(i)].pen().color().name() for i in range(3)]==['#12ab34','#654321','#12ab34']
    assert all(not item.highlighted and item.brush().color().alpha()==0 for item in items.values())
    w.project['classes'][0]['color']='#aa22dd';w.redraw()
    assert items['0'].pen().color().name()=='#aa22dd' and items['1'].pen().color().name()=='#654321'
    assert all(w.view.overlay_records[key] is item and item.path()==paths[key] for key,item in items.items())
    w.selected_ids={'0'};w.redraw();assert items['0'].pen().color().name()==SELECTION and items['0'].highlighted
    w.selected_ids.clear();w.draft={'base_id':'2','geometry':w.project['labels'][2]['geometry']};w.redraw()
    assert w.view.overlay_records['__draft'].pen().color().name()==EDITING
    assert not errors
