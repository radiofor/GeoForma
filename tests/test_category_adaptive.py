"""Adaptive category buttons use only their required space and remain clickable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from geoforma.ui.category_buttons import CategoryButtons,ACTIVE_ROLE


@pytest.mark.parametrize('width',[220,320,480])
@pytest.mark.parametrize('count',[0,1,2,3,4,5,6,7,12])
def test_categories_fill_each_row_and_use_only_needed_height(width,count):
    app=QApplication.instance() or QApplication([]);buttons=CategoryButtons();buttons.setFixedWidth(width);buttons.show()
    buttons.sync([{'id':i,'name':'类别 '+str(i)} for i in range(1,count+1)],1 if count else None,True)
    for _ in range(5):app.processEvents()
    assert buttons.height()==min(buttons.rowCount(),3)*buttons.row_height
    assert buttons.verticalScrollBar().maximum()==max(0,buttons.rowCount()-3)*buttons.row_height
    for row in range(buttons.rowCount()):
        items=[buttons.items[i] for i in range(1,count+1) if buttons.items[i].row()==row]
        rects=[buttons.visualItemRect(item) for item in items]
        assert rects[0].left()==0 and rects[-1].right()==buttons.viewport().width()-1
        assert max(rect.width() for rect in rects)-min(rect.width() for rect in rects)<=2
        assert all(left.right()+1==right.left() for left,right in zip(rects,rects[1:]))
    buttons.close()


def test_resize_reuses_items_and_scrolls_to_the_selected_category():
    app=QApplication.instance() or QApplication([]);buttons=CategoryButtons();buttons.setFixedWidth(220);buttons.show()
    categories=[{'id':i,'name':'类别 '+str(i)} for i in range(1,10)]
    buttons.sync(categories,1,True)
    for _ in range(4):app.processEvents()
    original=dict(buttons.items);buttons.setFixedWidth(480)
    for _ in range(4):app.processEvents()
    assert buttons._columns==3 and all(buttons.items[key] is item for key,item in original.items())
    buttons.sync(categories,9,True);app.processEvents()
    item=buttons.items[9];assert item.data(ACTIVE_ROLE) and buttons.viewport().rect().intersects(buttons.visualItemRect(item))
    buttons.setFixedWidth(220)
    for _ in range(4):app.processEvents()
    assert buttons.viewport().rect().intersects(buttons.visualItemRect(item))
    events=[];buttons.requested.connect(events.append)
    rect=buttons.visualItemRect(item)
    position=QPoint(rect.right()-4,rect.center().y())
    assert buttons.itemAt(position) is item
    QTest.mouseClick(buttons.viewport(),Qt.MouseButton.LeftButton,pos=position);app.processEvents()
    assert events==[9]
    buttons.close()


def test_font_change_expands_rows_without_empty_space():
    app=QApplication.instance() or QApplication([]);buttons=CategoryButtons();buttons.resize(320,100);buttons.show()
    buttons.sync([{'id':1,'name':'很长的类别名称'}],1,True);app.processEvents()
    font=buttons.font();font.setPointSize(22);buttons.setFont(font)
    for _ in range(4):app.processEvents()
    assert buttons.row_height>=buttons.fontMetrics().height()+16
    assert buttons.height()==buttons.row_height and buttons.verticalScrollBar().maximum()==0
    buttons.close()
