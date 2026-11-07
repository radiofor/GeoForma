"""Draw a polygon directly in image pixel coordinates, without model inference."""
import copy
import math
from datetime import datetime
from shapely.geometry import Polygon,mapping


class ManualPolygonWorkflow:
    def add_manual_vertex(self,x,y):
        from ..operation_state import interaction_locked
        if interaction_locked(self) or not self.image or self.foreground_task_active() or self.reshape_session is not None or not self.raw_view_action.isChecked():return
        from ..tool_state import has_unsaved_annotation
        if has_unsaved_annotation(self.draft) and not self.draft.get('manual_vertices'):
            self.statusBar().showMessage('请先保存或取消当前标签，再绘制新多边形。',4000);return
        points=self.draft.get('manual_vertices',[])
        if len(points)>=8192:
            self.statusBar().showMessage('多边形顶点过多，请先完成绘制。',4000);return
        if points and points[-1]==[x,y]:return
        if not points:
            self.selected_id=None;self.selected_ids.clear();self.prompt_undo=[];self.prompt_redo=[]
            self.draft={'manual_vertices':[],'editing_state':'manual','pending':True,'points':[]}
        self.prompt_undo.append(self.geometry_snapshot());self.prompt_redo=[]
        self.draft['manual_vertices'].append([x,y])
        self.sync_manual_polygon();self.update_draft_info();self.update_controls();self.mark_dirty()

    def undo_manual_vertex(self):
        points=self.draft.get('manual_vertices')
        if not points or self.foreground_task_active():return
        if self.restore_geometry_history(self.prompt_undo,self.prompt_redo):return
        points.pop()
        if not points:self.draft={}
        self.sync_manual_polygon();self.update_draft_info();self.update_controls();self.mark_dirty()

    def cancel_manual_polygon(self):
        if 'manual_vertices' in self.draft or self.draft.get('source')=='manual_draw' and not self.draft.get('base_id'):self.clear_draft()

    def finish_manual_polygon(self):
        points=self.draft.get('manual_vertices')
        if not points or self.foreground_task_active():return
        if len(set(map(tuple,points)))<3:
            self.statusBar().showMessage('请至少绘制三个不同的顶点。',4000);return
        polygon=Polygon(points)
        if polygon.is_empty or not polygon.is_valid or polygon.area<=0:
            self.statusBar().report_error('多边形无效，请撤回顶点并避免边界交叉。',source='manual_polygon');return
        from ..pixel_geometry import pixel_contour
        image={key:self.image[key] for key in ('width','height')};source=mapping(polygon)
        single=self.single_polygon.isChecked();context=self.annotation_context();vertices=copy.deepcopy(points);draft=self.draft
        def current():
            return (self.draft is draft and self.annotation_context()==context and self.draft.get('manual_vertices')==vertices
                    and self.single_polygon.isChecked()==single and self.image is not None
                    and all(self.image[key]==image[key] for key in image))
        def convert(task=None):
            geometry=pixel_contour(source,image,task)
            if single:
                from ..single_polygon import select_polygon
                geometry=select_polygon(geometry)
            return geometry
        def publish(geometry):
            if not current():return
            self.commit_manual_polygon(geometry)
        x0,y0,x1,y1=polygon.bounds
        area=max(0,min(image['width'],math.ceil(x1))-max(0,math.floor(x0)))*max(0,min(image['height'],math.ceil(y1))-max(0,math.floor(y0)))
        if area>65536:
            def work(task):
                try:return convert(task),None
                except ValueError as error:return None,str(error)
            def done(result):
                geometry,error=result
                if not current():return
                if error:self.task_outcome='failed';self.log_message(error);self.statusBar().report_error('生成多边形失败：'+error,source='manual_polygon')
                else:publish(geometry)
            self.run('生成多边形',work,done,kind='manual_polygon',deferred_valid=current);return
        try:publish(convert())
        except ValueError as error:
            self.log_message(str(error));self.statusBar().report_error('生成多边形失败：'+str(error),source='manual_polygon')

    def commit_manual_polygon(self,geometry):
        self.draft={'geometry':geometry,'points':[],'box':None,'pending':False,
                    'editing_state':'manual','source':'manual_draw',
                    'manual_edits':[{'tool':'draw_polygon','at':datetime.now().isoformat()}]}
        self.prompt_undo=[{'_draft':{}}];self.prompt_redo=[];self.view.clear_reshape()
        self.update_draft_info();self.refresh_labels();self.update_controls();self.mark_dirty()

    def sync_manual_polygon(self):
        points=self.draft.get('manual_vertices')
        if points:self.view.set_polygon_stroke(points)
        elif self.reshape_session is None and self.view.mode in ('draw_polygon','pan') and self.view.reshape_items:self.view.clear_reshape()
