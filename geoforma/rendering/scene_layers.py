"""Incremental graphics layers; no annotation state or model inference."""
from PySide6.QtCore import Qt, QRectF, QPointF,QVariantAnimation
from PySide6.QtGui import QImage, QPixmap, QPainterPath, QPainterPathStroker, QPen, QColor, QTransform
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsPixmapItem
from collections import OrderedDict
from .label_item import LabelItem, LABEL_RED


def geometry_path(geometry):
    path=QPainterPath();path.setFillRule(Qt.FillRule.OddEvenFill)
    polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    for polygon in polygons:
        for ring in polygon:
            if not ring:continue
            path.moveTo(*ring[0])
            for point in ring[1:]:path.lineTo(*point[:2])
            path.closeSubpath()
    return path


class BoundedPreviewItem(QGraphicsPixmapItem):
    clip_rect=None

    def paint(self,painter,option,widget=None):
        painter.save()
        if self.clip_rect is not None:painter.setClipRect(self.clip_rect,Qt.ClipOperation.IntersectClip)
        super().paint(painter,option,widget)
        painter.restore()


class RasterOverviewItem(QGraphicsPixmapItem):
    """Leave the detail window transparent instead of showing stale overview pixels."""
    excluded=None

    def paint(self,painter,option,widget=None):
        if self.excluded is None:
            super().paint(painter,option,widget);return
        path=QPainterPath();path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(self.boundingRect());path.addRect(self.excluded)
        painter.save();painter.setClipPath(path,Qt.ClipOperation.IntersectClip)
        super().paint(painter,option,widget);painter.restore()


class SceneLayers:
    def __init__(self,view):
        self.view=view;self.reset()

    def reset(self):
        self.base_item=None;self.detail_item=None;self.preview_item=None;self.overlay_records={};self.overlay_items=[];self.prompt_items=[];self.point_records={};self.box_item=None;self.path_cache=OrderedDict();self.overlay_visible=True
        self.raster_epoch=None
        self.annotation_context=None;self.annotation_sets={}
        self.raster_fade=None;self.raster_backups=[]

    def stop_raster_transition(self):
        if self.raster_fade is not None:self.raster_fade.stop();self.raster_fade.deleteLater();self.raster_fade=None
        if self.base_item is not None:self.base_item.setOpacity(1)
        for item in self.raster_backups:self.scene().removeItem(item)
        self.raster_backups=[]

    def begin_raster_transition(self):
        self.stop_raster_transition()
        for z,item in enumerate((self.base_item,self.detail_item)):
            if item is None:continue
            backup=RasterOverviewItem(item.pixmap()) if isinstance(item,RasterOverviewItem) else QGraphicsPixmapItem(item.pixmap())
            if isinstance(backup,RasterOverviewItem):backup.excluded=item.excluded
            backup.setPos(item.pos());backup.setTransform(item.transform());backup.setZValue(z-2)
            backup.setTransformationMode(item.transformationMode());self.scene().addItem(backup);self.raster_backups.append(backup)

    def finish_raster_transition(self):
        if not self.raster_backups or self.base_item is None:return
        self.base_item.setOpacity(0)
        animation=QVariantAnimation(self.view);self.raster_fade=animation;animation.setDuration(140);animation.setStartValue(0.);animation.setEndValue(1.)
        animation.valueChanged.connect(lambda value:self.base_item.setOpacity(value))
        animation.finished.connect(self.stop_raster_transition);animation.start()

    def set_annotation_context(self,context):
        if context==self.annotation_context:return
        self.annotation_sets[self.annotation_context]={'overlays':self.overlay_records,'points':self.point_records,'box':self.box_item}
        for item in self.overlay_items+self.prompt_items:item.setVisible(False)
        self.clear_preview()
        self.annotation_context=context
        state=self.annotation_sets.setdefault(context,{'overlays':{},'points':{},'box':None})
        self.overlay_records=state['overlays'];self.point_records=state['points'];self.box_item=state['box']
        self.overlay_items=list(self.overlay_records.values());self.prompt_items=list(self.point_records.values())+([self.box_item] if self.box_item is not None else [])
        for item in self.overlay_items+self.prompt_items:item.setVisible(self.overlay_visible)

    def clear_detail(self):
        if self.detail_item is not None:self.scene().removeItem(self.detail_item);self.detail_item=None
        self.update_overview_clip()

    def update_overview_clip(self):
        if self.base_item is None:return
        self.base_item.excluded=self.base_item.mapFromItem(self.detail_item,self.detail_item.boundingRect()).boundingRect() if self.detail_item is not None else None
        self.base_item.update()

    def scene(self):return self.view.scene()
    def mapToScene(self,*args):return self.view.mapToScene(*args)
    def viewport(self):return self.view.viewport()
    def transform(self):return self.view.transform()

    def show_raster(self,array,valid,window,overview=False):
        import numpy as np
        rgba=np.dstack([array,valid.astype(np.uint8)*255]);h,w=rgba.shape[:2]
        image=QImage(rgba.data,w,h,rgba.strides[0],QImage.Format.Format_RGBA8888).copy()
        current=self.base_item if overview else self.detail_item
        if current:current.setPixmap(QPixmap.fromImage(image));item=current
        elif overview:
            item=RasterOverviewItem(QPixmap.fromImage(image));self.scene().addItem(item)
        else:item=self.scene().addPixmap(QPixmap.fromImage(image))
        item.setPos(window[0],window[1]);item.setTransform(QTransform.fromScale(window[2]/w,window[3]/h));item.setZValue(0 if overview else 1)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        if overview:self.base_item=item
        else:self.detail_item=item
        self.update_overview_clip()

    def clear_preview(self):
        if self.preview_item is not None:self.scene().removeItem(self.preview_item);self.preview_item=None

    def show_preview(self,mask,window,box=None):
        import numpy as np
        rgba=np.zeros((*mask.shape,4),dtype=np.uint8);rgba[:,:,:3]=[84,215,255];rgba[:,:,3]=np.where(mask,85,0)
        h,w=mask.shape;im=QImage(rgba.data,w,h,rgba.strides[0],QImage.Format.Format_RGBA8888).copy()
        if self.preview_item is None:
            self.preview_item=BoundedPreviewItem(QPixmap.fromImage(im));self.scene().addItem(self.preview_item)
        else:self.preview_item.setPixmap(QPixmap.fromImage(im))
        self.preview_item.clip_rect=QRectF((box[0]-window[0])*w/window[2],(box[1]-window[1])*h/window[3],(box[2]-box[0])*w/window[2],(box[3]-box[1])*h/window[3]) if box else None
        self.preview_item.setPos(window[0],window[1]);self.preview_item.setTransform(QTransform.fromScale(window[2]/w,window[3]/h));self.preview_item.setZValue(14);self.preview_item.setVisible(self.overlay_visible)
        self.preview_item.update()

    def cached_path(self,geometry):
        key=id(geometry);cached=self.path_cache.get(key)
        if cached and cached[0] is geometry:self.path_cache.move_to_end(key);return cached[1]
        path=geometry_path(geometry);self.path_cache[key]=(geometry,path)
        if len(self.path_cache)>512:self.path_cache.popitem(last=False)
        return path

    def set_overlay_visibility(self,visible):
        self.overlay_visible=visible
        for item in self.overlay_items+self.prompt_items:item.setVisible(visible)
        if self.preview_item is not None:self.preview_item.setVisible(visible)

    def overlays(self,labels,draft=None,selected=None,pending=False,draft_id=None,editing_id=None,class_colors=None):
        from ..theme import SELECTION, EDITING
        selected=selected or ()
        requested=set()
        for label in labels:
            key=label['id'];requested.add(key)
            highlight=label['id'] in selected
            editing=key in editing_id if isinstance(editing_id,set) else key==editing_id
            item=self.overlay_records.get(key)
            if item is None:
                # Prepare the whole active annotation layer before publishing it;
                # Qt clips painting, so zooming never creates missing items.
                item=LabelItem();self.scene().addItem(item);self.overlay_records[key]=item
            if getattr(item,'geometry_value',None) is not label['geometry']:
                source=label.get('_source_geometry',label['geometry'])
                if label['geometry'] is getattr(item,'source_geometry',None):path=item.source_path
                else:
                    path=label.get('_render_path')
                    if path is None:path=self.cached_path(label['geometry'])
                item.setPath(path);item.geometry_value=label['geometry']
                if source is label['geometry']:item.source_geometry=source;item.source_path=path
                elif '_source_path' in label:item.source_geometry=source;item.source_path=label['_source_path']
            category_color=(class_colors or {}).get(label.get('class_id'),LABEL_RED)
            color=QColor(SELECTION if highlight else EDITING if editing else category_color)
            state=(label['status'],highlight,bool(label.get('edge')),editing,color.name())
            if getattr(item,'render_state',None)!=state:
                item.highlighted=highlight or editing
                pen=QPen(color,3 if highlight or editing else 1.4,Qt.PenStyle.DashLine);pen.setCosmetic(True);item.setPen(pen)
                fill=QColor(color);fill.setAlpha(0);item.setBrush(fill);item.setZValue(15 if editing else 12 if highlight else 10);item.render_state=state
            if item.data(0)!=label['id']:item.setData(0,label['id'])
            if item.isVisible()!=self.overlay_visible:item.setVisible(self.overlay_visible)
        if draft:
            requested.add('__draft');item=self.overlay_records.get('__draft')
            if item is None:item=LabelItem();self.scene().addItem(item);self.overlay_records['__draft']=item
            if getattr(item,'geometry_value',None) is not draft:item.setPath(self.cached_path(draft));item.geometry_value=draft
            highlight=draft_id is not None and draft_id in selected;state=('editing',highlight)
            if getattr(item,'render_state',None)!=state:
                item.highlighted=True
                color=QColor(SELECTION if highlight else EDITING);pen=QPen(color,3,Qt.PenStyle.DashLine);pen.setCosmetic(True);item.setPen(pen)
                color.setAlpha(0);item.setBrush(color);item.render_state=state
            item.setZValue(15);item.setData(0,draft_id);item.setVisible(self.overlay_visible)
        for key in set(self.overlay_records)-requested:self.scene().removeItem(self.overlay_records.pop(key))
        self.overlay_items=list(self.overlay_records.values())

    def prompts(self,points,box=None,selected=None):
        from ..theme import SELECTION
        for index,(x,y,label) in enumerate(points):
            item=self.point_records.get(index)
            if item is None:
                item=QGraphicsEllipseItem();item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations);self.scene().addItem(item);self.point_records[index]=item;item.setZValue(20);item.setData(1,index)
            highlight=index in (selected or set());state=(x,y,label,highlight)
            if getattr(item,'render_state',None)!=state:
                radius=6 if highlight else 4;item.setRect(-radius,-radius,2*radius,2*radius);item.setPos(x,y)
                item.setBrush(QColor('#63ff85' if label else '#ff526d'));item.setPen(QPen(QColor(SELECTION if highlight else 'white'),3 if highlight else 1));item.render_state=state
            item.setVisible(self.overlay_visible)
        for index in set(self.point_records)-set(range(len(points))):self.scene().removeItem(self.point_records.pop(index))
        if box:
            if self.box_item is None:
                self.box_item=QGraphicsRectItem();pen=QPen(QColor('#54d7ff'),2,Qt.PenStyle.DashLine);pen.setCosmetic(True);self.box_item.setPen(pen);self.box_item.setZValue(20);self.scene().addItem(self.box_item)
            self.box_item.setRect(QRectF(QPointF(box[0],box[1]),QPointF(box[2],box[3])));self.box_item.setVisible(self.overlay_visible)
        elif self.box_item is not None:self.scene().removeItem(self.box_item);self.box_item=None
        self.prompt_items=list(self.point_records.values())+([self.box_item] if self.box_item is not None else [])

    def hit_label(self,position):
        point=self.mapToScene(position);stroker=QPainterPathStroker();stroker.setWidth(8/max(self.transform().m11(),1e-6))
        radius=stroker.width()/2;search=QRectF(point.x()-radius,point.y()-radius,2*radius,2*radius)
        # Query the spatial scene index instead of scanning all retained labels.
        items=self.scene().items(search,Qt.ItemSelectionMode.IntersectsItemBoundingRect,Qt.SortOrder.DescendingOrder,self.transform())
        for item in items:
            if not isinstance(item,QGraphicsPathItem) or not item.isVisible() or item.data(0) is None:continue
            if not item.path().boundingRect().adjusted(-radius,-radius,radius,radius).contains(point):continue
            if item.path().contains(point) or stroker.createStroke(item.path()).contains(point):return item.data(0)
        return None

