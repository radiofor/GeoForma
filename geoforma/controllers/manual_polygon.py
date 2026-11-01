"""Draw a polygon directly in image pixel coordinates, without model inference."""
import copy
from datetime import datetime
from shapely.geometry import Polygon,mapping


class ManualPolygonWorkflow:
    def add_manual_vertex(self,x,y):
        if not self.image or self.foreground_task_active() or not self.raw_view_action.isChecked():return
        if self.draft and 'manual_vertices' not in self.draft:
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
            self.statusBar().showMessage('多边形无效，请撤回顶点并避免边界交叉。',5000);return
        vertices=copy.deepcopy(points)
        self.draft={'geometry':mapping(polygon),'points':[],'box':None,'pending':False,
                    'editing_state':'manual','source':'manual_draw',
                    'manual_edits':[{'tool':'draw_polygon','vertices':vertices,'at':datetime.now().isoformat()}]}
        self.prompt_undo=[{'_draft':{}}];self.prompt_redo=[];self.view.clear_reshape()
        self.update_draft_info();self.refresh_labels();self.update_controls();self.mark_dirty()
        self.statusBar().showMessage('多边形已绘制，可选择类别并保存标签。',4000)

    def sync_manual_polygon(self):
        points=self.draft.get('manual_vertices')
        if points:self.view.set_polygon_stroke(points)
        elif self.reshape_session is None and self.view.mode in ('draw_polygon','pan') and self.view.reshape_items:self.view.clear_reshape()
