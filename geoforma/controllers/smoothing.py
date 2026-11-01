"""Mode-local smoothing previews leave canonical pixel contours and undo data intact."""
from ..smoothing import settings,smooth_batch


class SmoothingWorkflow:
    def smoothing_changed(self):
        if self.restoring_project:return
        self.project.setdefault('smoothing',{})[self.annotation_mode()]={'enabled':self.smooth_enabled.isChecked(),'value':self.smooth_value.value()}
        if not self.smooth_enabled.isChecked():self.smoother.stop()
        self.mark_dirty();self.redraw();self.update_controls()

    def sync_smoothing_controls(self):
        config=settings(self.project,self.annotation_mode())
        for control,value in ((self.smooth_enabled,config['enabled']),(self.smooth_value,config['value'])):
            blocked=control.blockSignals(True)
            if control is self.smooth_enabled:
                if control.isChecked()!=value:control.setChecked(value)
            elif control.value()!=value:control.setValue(value)
            control.blockSignals(blocked)
        self.smooth_enabled.setEnabled(self.reshape_session is None and not self.closing)
        self.smooth_value.setEnabled(config['enabled'] and self.smooth_enabled.isEnabled())

    def smoothing_sources(self,labels,draft):
        # Include hidden confirmed labels so a display filter cannot change topology.
        if self.candidate_index:
            saved,candidates=self.candidate_index.visible({})
            live={l['id'] for l in self.current_batch_labels()};sources=[l for l in saved+candidates if l['id'] in live]
        else:sources=list(labels)
        from ..editing_state import batch_labels
        sources=batch_labels(sources,self.draft)
        base=self.draft.get('base_id')
        if draft:
            sources=[l for l in sources if l['id']!=base]
            sources.append({'id':'__draft','geometry':draft,'box':self.draft.get('box'),'status':'draft','editing_state':self.draft.get('editing_state','model'),
                'model':{'single_polygon':self.mode_index==0 and self.single_polygon.isChecked()}})
        return sources

    def smooth_display(self,labels,draft):
        config=settings(self.project,self.annotation_mode())
        if not config['enabled'] or not self.image:
            self.smoother.stop();return labels,draft
        sources=self.smoothing_sources(labels,draft)
        if not sources:return labels,draft
        key=self.smoothing_key(sources)
        image={k:self.image[k] for k in ('width','height','path','model_recipe') if k in self.image}
        result=self.smoother.request(key,sources,lambda task:smooth_batch(sources,config['value'],image,task))
        if result is None and self.smoother.last:
            old_key,old_sources,result=self.smoother.last
            if old_key[0]!=key[0]:result=None
            else:
                live={l['id']:l['geometry'] for l in sources}
                unchanged={l['id'] for l in old_sources if live.get(l['id']) is l['geometry']}
                result=[l for l in result if l['id'] in unchanged]
        derived={l['id']:l for l in result or ()}
        target=derived.get('__draft')
        if target:
            for geometry,path in ((target['geometry'],target['_render_path']),(target['_source_geometry'],target['_source_path'])):
                self.view.path_cache[id(geometry)]=(geometry,path)
                if len(self.view.path_cache)>512:self.view.path_cache.popitem(last=False)
        return [dict(l,**{key:derived[l['id']][key] for key in ('geometry','_bounds','_render_path','_source_geometry','_source_path')}) if l['id'] in derived else l for l in labels],derived.get('__draft',{}).get('geometry',draft)

    def smoothing_key(self,sources):
        config=settings(self.project,self.annotation_mode())
        return (self.annotation_context(),config['value'],(self.image.get('fingerprint'),id(self.image.get('model_recipe')),self.image['width'],self.image['height']),tuple((l['id'],id(l['geometry']),tuple(l.get('box') or ()),l.get('status'),l.get('editing_state','model'),l.get('model',{}).get('single_polygon')) for l in sources))

    def smoothing_updated(self):
        if not self.closing:self.redraw();self.update_controls()

    def smoothing_error(self,message):
        self.log_message(message);self.statusBar().showMessage('平滑处理失败，请减小平滑值或关闭平滑。',5000)
