"""Mode-local smoothing previews leave canonical pixel contours and undo data intact."""
from ..smoothing import settings,smooth_batch


class SmoothingWorkflow:
    def retain_reshape_smoothing(self,replacements,updated_draft):
        """Keep the displayed smooth outlines until the new outlines are ready."""
        config=settings(self.project,self.annotation_mode())
        if not config['enabled'] or not self.image:
            self._reshape_smoothing_hold=None;return
        expected={part['id']:part['geometry'] for parts in replacements.values() for part in parts}
        if updated_draft is not None:expected['__draft']=updated_draft['geometry']
        if not expected:return
        last=self.smoother.last;old={}
        if last and last[0][:3]==self.smoothing_key([])[:3]:old={record['id']:record for record in last[2]}
        retained={}
        for identifier in expected:
            item=self.view.overlay_records.get(identifier);record=old.get(identifier)
            if item is not None and record and item.geometry_value is record['geometry']:
                retained[identifier]=record
            elif item is not None and getattr(item,'geometry_value',None) is not None:
                path=item.path();bounds=path.boundingRect();geometry=item.geometry_value
                retained[identifier]={'geometry':geometry,'_bounds':[bounds.left(),bounds.top(),bounds.right(),bounds.bottom()],
                                      '_render_path':path,'_source_geometry':geometry,'_source_path':path}
            else:retained[identifier]=None
        draft_id=(updated_draft.get('base_id') or next(iter(updated_draft.get('display_ids',[])),None)) if updated_draft is not None else None
        self._reshape_smoothing_hold=(self.annotation_context(),config['value'],expected,retained,draft_id)

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
        if self.label_index:
            saved=self.label_index.visible({})
            live={l['id'] for l in self.current_labels()};sources=[l for l in saved if l['id'] in live]
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
            self._reshape_smoothing_hold=None;self.smoother.stop();return labels,draft
        sources=self.smoothing_sources(labels,draft)
        if not sources:return labels,draft
        key=self.smoothing_key(sources)
        hold=getattr(self,'_reshape_smoothing_hold',None)
        if hold:
            live={label['id']:label['geometry'] for label in self.current_labels()}
            if self.draft.get('geometry'):live['__draft']=self.draft['geometry']
            if hold[0]!=self.annotation_context() or hold[1]!=config['value']:
                self._reshape_smoothing_hold=None;hold=None
            else:
                expected=dict(hold[2]);retained=dict(hold[3]);draft_id=hold[4]
                if '__draft' in expected and '__draft' not in live and draft_id in live:
                    expected[draft_id]=live[draft_id];retained[draft_id]=retained['__draft']
                expected={identifier:live[identifier] for identifier in expected if identifier in live}
                retained={identifier:retained[identifier] for identifier in expected}
                hold=(hold[0],hold[1],expected,retained,draft_id) if expected else None
                self._reshape_smoothing_hold=hold
        image={k:self.image[k] for k in ('width','height','path','model_recipe') if k in self.image}
        result=self.smoother.request(key,sources,lambda task:smooth_batch(sources,config['value'],image,task))
        source_geometry={label['id']:label['geometry'] for label in sources}
        if hold and result is not None and all(source_geometry.get(i) is geometry for i,geometry in hold[2].items()):
            self._reshape_smoothing_hold=None;hold=None
        if result is None and self.smoother.last:
            old_key,old_sources,result=self.smoother.last
            if old_key[0]!=key[0]:result=None
            else:
                live={l['id']:l['geometry'] for l in sources}
                unchanged={l['id'] for l in old_sources if live.get(l['id']) is l['geometry']}
                result=[l for l in result if l['id'] in unchanged]
        derived={l['id']:l for l in result or ()}
        if hold:
            for identifier,record in hold[3].items():
                if record is None:derived.pop(identifier,None)
                else:derived[identifier]=record
            labels=[label for label in labels if label['id'] not in hold[2] or label['id'] in derived]
            if '__draft' in hold[2] and '__draft' not in derived:draft=None
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
        self._reshape_smoothing_hold=None
        self.log_message(message);self.statusBar().showMessage('平滑处理失败，请减小平滑值或关闭平滑。',5000)
        self.redraw()
