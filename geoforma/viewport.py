from PySide6.QtCore import Qt, Signal, QRectF
from .ui.text import ui_text
from PySide6.QtGui import QPainterPath, QPen, QColor, QPainter, QBrush
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QWidget, QVBoxLayout, QLabel


from .rendering.scene_layers import SceneLayers
from .rendering.navigation import ViewNavigation


class ImageView(ViewNavigation,QGraphicsView):
    point=Signal(float,float,int)
    box=Signal(object)
    reshapePoint=Signal(float,float)
    reshapeTarget=Signal(str)
    reshapeFinished=Signal()
    reshapeUndo=Signal()
    reshapeCancelled=Signal()
    polygonPoint=Signal(float,float)
    polygonFinished=Signal()
    polygonUndo=Signal()
    polygonCancelled=Signal()
    selected=Signal(str)
    selection=Signal(str,object,bool,bool)
    viewportChanged=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.setScene(QGraphicsScene(self));self.mode='pan';self.selected_mode='pan';self.raster_rect=QRectF()
        self.layers=SceneLayers(self);self.drag_start=None;self.rubber=None;self.drag_pixel=None;self.drag_add=False
        self.middle_drag=None
        self.pan_press=None
        self.reshape_enabled=False;self.reshape_picking=False;self.reshape_points=[];self.reshape_items=[];self.polygon_fill=None
        from .theme import CANVAS
        self.setBackgroundBrush(QColor(CANVAS));self.setRenderHint(QPainter.RenderHint.Antialiasing);self.setFrameShape(self.Shape.NoFrame)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse);self.setMouseTracking(True)
        from .branding import application_icon
        self.empty=QWidget(self.viewport());self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);layout=QVBoxLayout(self.empty);layout.setContentsMargins(0,0,0,0)
        mark=QLabel();mark.setPixmap(application_icon().pixmap(110,110));mark.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(mark)
        title=QLabel('GeoForma');title.setAlignment(Qt.AlignmentFlag.AlignCenter);title.setStyleSheet('color:#dcebef;font-family:"Segoe UI";font-size:28px;font-weight:600;');layout.addWidget(title)
        self.empty.resize(240,165)
        self.loading=QLabel(ui_text('viewport.loading'),self.viewport());self.loading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.loading.setStyleSheet('color:#dcebef;background:#173b4c;border-radius:7px;padding:10px 16px;');self.loading.hide()
        self.initialize_navigation()
        self.set_mode('pan')

    def drawBackground(self,painter,rect):
        super().drawBackground(painter,rect)
        from .theme import draw_grid_pattern
        painter.save();painter.resetTransform();draw_grid_pattern(painter,QRectF(self.viewport().rect()));painter.restore()




    def set_mode(self,mode):
        self.selected_mode=mode
        self.clear_preview()
        if self.rubber is not None:self.scene().removeItem(self.rubber);self.rubber=None
        self.drag_start=None
        self.mode=mode;self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode=='pan' else QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.OpenHandCursor if mode=='pan' else Qt.CursorShape.CrossCursor)

    def set_image(self,width,height):
        self.layers.stop_raster_transition()
        self.scene().clear();self.layers.reset();self.rubber=None
        self.reshape_points=[];self.reshape_items=[];self.reshape_enabled=False;self.polygon_fill=None
        self.raster_rect=QRectF(0,0,width,height);self.scene().setSceneRect(self.raster_rect);self.setSceneRect(self.raster_rect);self.fit_image()
        self.empty.setVisible(width==0 or height==0)
        self.loading.setText(ui_text('viewport.loading'));self.loading.adjustSize();self.loading.move((self.viewport().width()-self.loading.width())//2,(self.viewport().height()-self.loading.height())//2);self.loading.setVisible(width>0 and height>0)
        if self.raster_rect.isEmpty():self.resetTransform()


    def show_raster(self, array, valid, window, overview=False):
        result=self.layers.show_raster(array,valid,window,overview);self.loading.hide();return result

    def show_raster_error(self):
        if self.layers.base_item is None and self.layers.detail_item is None and not self.raster_rect.isEmpty():
            self.loading.setText(ui_text('viewport.load_failed'));self.loading.adjustSize();self.loading.show()
            self.loading.move((self.viewport().width()-self.loading.width())//2,(self.viewport().height()-self.loading.height())//2)

    def visible_window(self):
        r=self.mapToScene(self.viewport().rect()).boundingRect().intersected(self.raster_rect)
        return [int(r.left()),int(r.top()),max(1,int(r.width()+1)),max(1,int(r.height()+1))]

    def clear_preview(self):return self.layers.clear_preview()

    def show_preview(self, mask, window,box=None):return self.layers.show_preview(mask,window,box)

    def cached_path(self, geometry):return self.layers.cached_path(geometry)

    def set_overlay_visibility(self, visible):
        self.layers.set_overlay_visibility(visible)
        for item in self.reshape_items:item.setVisible(visible)
        if self.polygon_fill:self.polygon_fill.setVisible(visible)

    def set_annotation_context(self,context):return self.layers.set_annotation_context(context)

    def overlays(self, labels, draft=None, selected=None, pending=False, draft_id=None, editing_id=None,class_colors=None):return self.layers.overlays(labels,draft,selected,pending,draft_id,editing_id,class_colors)

    def prompts(self, points, box=None, selected=None):return self.layers.prompts(points,box,selected)

    def hit_label(self, position):return self.layers.hit_label(position)

    def clear_reshape(self):
        for item in self.reshape_items:self.scene().removeItem(item)
        if self.polygon_fill:self.scene().removeItem(self.polygon_fill);self.polygon_fill=None
        self.reshape_items=[];self.reshape_points=[]

    def set_reshape_stroke(self,points,cursor=None):
        self.reshape_points=list(points);path=QPainterPath()
        if points:
            path.moveTo(*points[0])
            for p in points[1:]:path.lineTo(*p)
            if cursor is not None:path.lineTo(cursor.x(),cursor.y())
        if not self.reshape_items:
            for color,width,style in [('white',4,Qt.PenStyle.SolidLine),('#087f88',2,Qt.PenStyle.DashLine)]:
                item=self.scene().addPath(path);pen=QPen(QColor(color),width,style);pen.setCosmetic(True);item.setPen(pen);item.setZValue(27);item.setVisible(self.overlay_visible);self.reshape_items.append(item)
        else:
            for item in self.reshape_items:item.setPath(path)

    def set_polygon_stroke(self,points,cursor=None):
        self.set_reshape_stroke(points,cursor)
        if not points:return
        path=self.reshape_items[0].path();radius=3/max(abs(self.transform().m11()),1e-9)
        polygon=QPainterPath();polygon.moveTo(*points[0])
        for x,y in points[1:]:polygon.lineTo(x,y)
        if cursor is not None:polygon.lineTo(cursor.x(),cursor.y())
        if len(points)+(cursor is not None)>=3:
            polygon.closeSubpath();path.addPath(polygon)
        if self.polygon_fill is None:
            self.polygon_fill=self.scene().addPath(polygon,QPen(Qt.PenStyle.NoPen),QBrush(QColor(8,127,136,55)))
            self.polygon_fill.setZValue(26);self.polygon_fill.setVisible(self.overlay_visible)
        else:self.polygon_fill.setPath(polygon if len(points)+(cursor is not None)>=3 else QPainterPath())
        for x,y in points:path.addEllipse(QRectF(x-radius,y-radius,2*radius,2*radius))
        for item in self.reshape_items:item.setPath(path)

    def mousePressEvent(self,event):
        self.pan_press=event.position().toPoint() if self.mode=='pan' and event.button()==Qt.MouseButton.LeftButton else None
        if event.button()==Qt.MouseButton.MiddleButton:self.middle_drag=event.position().toPoint();self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept();return
        point=self.mapToScene(event.position().toPoint())
        if self.mode=='draw_polygon':
            if event.button()==Qt.MouseButton.RightButton:self.polygonFinished.emit()
            elif event.button()==Qt.MouseButton.LeftButton and self.raster_rect.contains(point):self.polygonPoint.emit(point.x(),point.y())
            event.accept();return
        if self.mode=='reshape':
            if self.reshape_enabled:
                if event.button()==Qt.MouseButton.RightButton:self.reshapeFinished.emit()
                elif event.button()==Qt.MouseButton.LeftButton and self.raster_rect.contains(point):self.reshapePoint.emit(point.x(),point.y())
            event.accept();return
        if event.button()==Qt.MouseButton.LeftButton and self.raster_rect.contains(point):
            if self.mode in ['positive','negative']:
                self.point.emit(point.x(),point.y(),1 if self.mode=='positive' else 0);return
        if event.button()==Qt.MouseButton.LeftButton and (self.mode in ['select','select_points'] or self.mode=='box' and self.raster_rect.contains(point)):
            self.drag_start=point;self.drag_pixel=event.position().toPoint();self.drag_add=bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier))
            pen=QPen(QColor('#54d7ff'),1,Qt.PenStyle.DashLine);pen.setCosmetic(True)
            self.rubber=self.scene().addRect(QRectF(point,point),pen);self.rubber.setZValue(25);return
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.middle_drag is not None:
            position=event.position().toPoint();delta=position-self.middle_drag;self.middle_drag=position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x());self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y());event.accept();return
        p=self.mapToScene(event.position().toPoint())
        if self.mode=='draw_polygon':
            if self.reshape_points:self.set_polygon_stroke(self.reshape_points,p)
            event.accept();return
        if self.mode=='reshape':
            if self.reshape_enabled:self.set_reshape_stroke(self.reshape_points,p)
            event.accept();return
        if self.drag_start is not None and self.rubber:
            r=QRectF(self.drag_start,p).normalized().intersected(self.raster_rect);self.rubber.setRect(r)
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self,event):
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self,event):
        if self.mode=='draw_polygon' and event.button()==Qt.MouseButton.LeftButton:
            point=self.mapToScene(event.position().toPoint())
            if self.raster_rect.contains(point):self.polygonPoint.emit(point.x(),point.y())
            self.polygonFinished.emit();event.accept();return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:self.middle_drag=None;self.setCursor(Qt.CursorShape.OpenHandCursor if self.mode=='pan' else Qt.CursorShape.CrossCursor);self.viewportChanged.emit();event.accept();return
        if self.drag_start is not None and self.rubber:
            r=self.rubber.rect();self.scene().removeItem(self.rubber);self.rubber=None;self.drag_start=None
            if self.mode=='box':
                self.clear_preview()
                if r.width()>2 and r.height()>2:self.box.emit([r.left(),r.top(),r.right(),r.bottom()])
            else:
                click=(event.position().toPoint()-self.drag_pixel).manhattanLength()<5;ids=[]
                if click:
                    if self.mode=='select':
                        value=self.hit_label(event.position().toPoint());ids=[value] if value is not None else []
                    else:
                        for item in self.items(event.position().toPoint()):
                            value=item.data(1)
                            if value is not None:ids=[value];break
                elif self.mode=='select_points':ids=[item.data(1) for item in self.prompt_items if item.data(1) is not None and r.contains(item.pos())]
                else:
                    path=QPainterPath();path.addRect(r)
                    ids=[item.data(0) for item in self.overlay_items if item.data(0) is not None and item.path().intersects(path)]
                self.selection.emit('points' if self.mode=='select_points' else 'labels',ids,self.drag_add,click)
            return
        super().mouseReleaseEvent(event)
        if self.pan_press is not None and (event.position().toPoint()-self.pan_press).manhattanLength()<5:
            identifier=self.hit_label(event.position().toPoint())
            if identifier is not None:self.selection.emit('labels',[identifier],bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)),True)
        self.pan_press=None;self.viewportChanged.emit()




    def keyPressEvent(self,event):
        if self.mode=='draw_polygon':
            if event.key()==Qt.Key.Key_Backspace:self.polygonUndo.emit();event.accept();return
            if event.key()==Qt.Key.Key_Escape:self.polygonCancelled.emit();event.accept();return
        if self.mode=='reshape':
            if event.key()==Qt.Key.Key_Backspace:self.reshapeUndo.emit();event.accept();return
            if event.key()==Qt.Key.Key_Escape:self.reshapeCancelled.emit();event.accept();return
        super().keyPressEvent(event)

    def event(self,event):
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Type.ShortcutOverride and getattr(self,'mode',None) in ('reshape','draw_polygon') and event.key() in (Qt.Key.Key_Backspace,Qt.Key.Key_Escape):event.accept();return True
        return super().event(event)

    @property
    def base_item(self):return self.layers.base_item

    @property
    def detail_item(self):return self.layers.detail_item

    @property
    def preview_item(self):return self.layers.preview_item

    @property
    def overlay_records(self):return self.layers.overlay_records

    @property
    def overlay_items(self):return self.layers.overlay_items

    @property
    def prompt_items(self):return self.layers.prompt_items

    @property
    def point_records(self):return self.layers.point_records

    @property
    def box_item(self):return self.layers.box_item

    @property
    def path_cache(self):return self.layers.path_cache

    @property
    def overlay_visible(self):return self.layers.overlay_visible
