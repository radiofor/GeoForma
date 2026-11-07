"""Mode-local smoothing previews leave canonical pixel contours and undo data intact."""
from ..smoothing import settings


class SmoothingWorkflow:
    def retain_reshape_smoothing(self,replacements):
        """Keep the displayed smooth outlines until the new outlines are ready."""
        config=settings(self.project,self.annotation_mode())
        if not (config['enabled'] or self.fill_holes.isChecked()) or not self.image:
            self._reshape_smoothing_hold=None;return
        expected={part['id']:part['geometry'] for parts in replacements.values() for part in parts}
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
        self._reshape_smoothing_hold=(self.annotation_context(),(config['enabled'],config['value'],self.fill_holes.isChecked()),expected,retained)

    def presentation_options_changed(self):
        """Switch the current representation without touching source geometry."""
        self._presentation_failed_context=None
        from ..rendering.label_transition import LabelTransition
        transition=getattr(self.view,'label_transition',None)
        if transition is None:
            transition=LabelTransition(self.view);self.view.label_transition=transition
        previous=transition.capture();self._presentation_transition_pending=True
        self._presentation_transition_context=self.annotation_context()
        self.redraw()
        if getattr(self,'_presentation_ready',True):
            self._presentation_transition_pending=False;transition.reveal(previous)

    def smoothing_changed(self):
        if self.restoring_project:return
        self.project.setdefault('smoothing',{})[self.annotation_mode()]={'enabled':self.smooth_enabled.isChecked(),'value':self.smooth_value.value()}
        self.mark_dirty();self.presentation_options_changed();self.update_controls()

    def sync_smoothing_controls(self):
        config=settings(self.project,self.annotation_mode())
        for control,value in ((self.smooth_enabled,config['enabled']),(self.smooth_value,config['value'])):
            blocked=control.blockSignals(True)
            if control is self.smooth_enabled:
                if control.isChecked()!=value:control.setChecked(value)
            elif control.value()!=value:control.setValue(value)
            control.blockSignals(blocked)
        self.smooth_enabled.setEnabled(not self.foreground_task_active() and not self.closing)
        self.smooth_value.setEnabled(config['enabled'] and self.smooth_enabled.isEnabled())

    def smoothing_sources(self,draft):
        # Include hidden confirmed labels so a display filter cannot change topology.
        current=self.current_labels()
        if self.label_index and self.label_index_key==self.label_index_signature(current):
            saved=self.label_index.visible({})
            live={l['id'] for l in current};sources=[l for l in saved if l['id'] in live]
        else:sources=list(current)
        from ..smoothing import smoothing_sources
        return smoothing_sources(sources,self.draft,draft)

    def smooth_display(self,labels,draft):
        self.smoother.set_context(self.annotation_context())
        config=settings(self.project,self.annotation_mode())
        if getattr(self,'_presentation_transition_pending',False) and getattr(self,'_presentation_transition_context',None)!=self.annotation_context():
            self._presentation_transition_pending=False
        fill=self.fill_holes.isChecked();self._presentation_ready=True
        if not (config['enabled'] or fill) or not self.image:
            if self.image and self.smoother.pinned:self.smoother.validate_pinned(self.smoothing_sources(draft))
            self._reshape_smoothing_hold=None;self.smoother.stop();return labels,draft
        sources=self.smoothing_sources(draft)
        if not sources:
            # A previous image may still be smoothing; do not spend CPU on a
            # result that cannot be displayed in the now-empty context.
            self._presentation_transition_pending=False;self._reshape_smoothing_hold=None;self.smoother.clear_pinned();self.smoother.stop();return labels,draft
        if not config['enabled'] and self.smoother.pinned:self.smoother.validate_pinned(sources)
        if not config['enabled'] and fill:
            from ..hole_filling import has_holes
            if not any(has_holes(label['geometry']) for label in sources):
                self._reshape_smoothing_hold=None;self.smoother.stop();return labels,draft
        key=self.smoothing_key(sources)
        hold=getattr(self,'_reshape_smoothing_hold',None)
        if hold:
            live={label['id']:label['geometry'] for label in self.current_labels()}
            if hold[0]!=self.annotation_context() or hold[1]!=(config['enabled'],config['value'],fill):
                self._reshape_smoothing_hold=None;hold=None
            else:
                expected=dict(hold[2]);retained=dict(hold[3])
                expected={identifier:live[identifier] for identifier in expected if identifier in live}
                retained={identifier:retained[identifier] for identifier in expected}
                hold=(hold[0],hold[1],expected,retained) if expected else None
                self._reshape_smoothing_hold=hold
        image={k:self.image[k] for k in ('width','height') if k in self.image}
        from ..label_presentation import presentation_batch
        result=self.smoother.request(key,sources,lambda task:presentation_batch(sources,fill,config,image,task,self.smoother.geometry_cache),immediate=bool(getattr(self,'_presentation_transition_pending',False)),retain=config['enabled'])
        self._presentation_ready=result is not None
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
        target=derived.get('__draft')
        if target:
            for geometry,path in ((target['geometry'],target['_render_path']),(target['_source_geometry'],target['_source_path'])):
                self.view.path_cache.put(geometry,path)
        return [dict(l,**{key:derived[l['id']][key] for key in ('geometry','_bounds','_render_path','_source_geometry','_source_path')}) if l['id'] in derived else l for l in labels],derived.get('__draft',{}).get('geometry',draft)

    def smoothing_key(self,sources):
        config=settings(self.project,self.annotation_mode())
        return (self.annotation_context(),config['value'],(self.image['width'],self.image['height']),config['enabled'],self.fill_holes.isChecked(),tuple((l['id'],id(l['geometry']),l.get('status')) for l in sources))

    def smoothing_updated(self):
        if self.closing:return
        self._presentation_failed_context=None
        transition=getattr(self.view,'label_transition',None)
        pending=(getattr(self,'_presentation_transition_pending',False) and
                 getattr(self,'_presentation_transition_context',None)==self.annotation_context())
        if not pending:self._presentation_transition_pending=False
        previous=transition.capture() if pending and transition is not None else None
        self.redraw()
        if previous is not None and getattr(self,'_presentation_ready',False):
            self._presentation_transition_pending=False;transition.reveal(previous)
        self.update_controls()

    def smoothing_error(self,message):
        if (getattr(self,'_presentation_transition_pending',False) and
            getattr(self,'_presentation_transition_context',None)==self.annotation_context()):
            self._presentation_failed_context=self.annotation_context()
        self._presentation_transition_pending=False;self._reshape_smoothing_hold=None
        self.log_message(message);self.statusBar().showMessage('平滑处理失败，请减小平滑值或关闭平滑。',5000)
        self.redraw();self.update_controls()
