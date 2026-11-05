"""Update raster rows in place without resetting selection or scroll positions."""
from dataclasses import dataclass
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QListWidgetItem

IDENTIFIER_ROLE=Qt.ItemDataRole.UserRole+1
REVIEW_COMPLETE_ROLE=Qt.ItemDataRole.UserRole+2


@dataclass(frozen=True)
class RasterRow:
    identifier:str
    title:str
    ready:bool
    detail:str
    review_complete:bool=False


class RasterListPresenter:
    def __init__(self,view):self.view=view;self.rows=();self.items={}

    def sync(self,rows,current=None,animate=False):
        rows=tuple(rows);view=self.view
        if rows==self.rows and (view.currentItem().data(IDENTIFIER_ROLE) if view.currentItem() else None)==current:return
        vertical=view.verticalScrollBar().value();horizontal=view.horizontalScrollBar().value()
        if animate:
            reveal=getattr(view.itemDelegate(),'reveal',None)
            if reveal:reveal([row.identifier for row in rows if row.identifier not in self.items])
        blocker=QSignalBlocker(view)
        try:
            wanted={row.identifier for row in rows}
            for identifier in tuple(self.items):
                if identifier not in wanted:
                    item=self.items.pop(identifier);view.takeItem(view.row(item))
            for index,row in enumerate(rows):
                item=self.items.get(row.identifier)
                if item is None:
                    item=QListWidgetItem();item.setData(IDENTIFIER_ROLE,row.identifier)
                    view.insertItem(index,item);self.items[row.identifier]=item
                elif view.row(item)!=index:
                    view.takeItem(view.row(item));view.insertItem(index,item)
                if item.text()!=row.title:item.setText(row.title)
                if item.data(Qt.ItemDataRole.UserRole)!=row.ready:item.setData(Qt.ItemDataRole.UserRole,row.ready)
                if item.data(REVIEW_COMPLETE_ROLE)!=row.review_complete:item.setData(REVIEW_COMPLETE_ROLE,row.review_complete)
                description='已完成' if row.review_complete else '未完成'
                if item.data(Qt.ItemDataRole.AccessibleDescriptionRole)!=description:item.setData(Qt.ItemDataRole.AccessibleDescriptionRole,description)
                if item.toolTip()!=row.detail:item.setToolTip(row.detail)
            chosen=self.items.get(current)
            if view.currentItem() is not chosen:view.setCurrentItem(chosen)
            view.verticalScrollBar().setValue(vertical);view.horizontalScrollBar().setValue(horizontal)
            self.rows=rows
        finally:del blocker
