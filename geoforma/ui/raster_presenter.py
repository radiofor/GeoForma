"""Update raster rows in place without resetting selection or scroll positions."""
from dataclasses import dataclass
from collections import Counter,defaultdict
from pathlib import Path
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


def build_raster_rows(images):
    """Prepare display rows in linear time even when many filenames repeat."""
    from .text import ui_text
    groups=defaultdict(list)
    for index,image in enumerate(images):groups[image['name']].append(index)
    titles=[image['name'] for image in images]
    for indices in groups.values():
        if len(indices)<2:continue
        parents={index:tuple(parent.name for parent in Path(images[index]['path']).parents) for index in indices}
        counts=Counter((depth,name) for values in parents.values() for depth,name in enumerate(values) if name)
        for index,values in parents.items():
            parent=next((name for depth,name in enumerate(values) if name and counts[(depth,name)]==1),None)
            if parent:titles[index]+=' · '+parent
    states={'queued':ui_text('control_state.update_controls.013'),'preparing':ui_text('control_state.update_controls.014'),
            'paused':ui_text('control_state.update_controls.015'),'failed':ui_text('control_state.update_controls.016'),
            'bands_required':ui_text('control_state.update_controls.017')}
    rows=[]
    for image,title in zip(images,titles):
        text=ui_text('control_state.update_controls.021') if image.get('ready') else states.get(image.get('preparation_state'),ui_text('images.refresh_images.017'))
        metadata=image.get('import_list',{});details=[image['path'],text]
        if metadata.get('group'):details.append('分组：'+metadata['group'])
        if metadata.get('note'):details.append('备注：'+metadata['note'])
        rows.append(RasterRow(image['id'],title,bool(image.get('ready')),'\n'.join(details),image.get('review_complete',False)))
    return rows


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
