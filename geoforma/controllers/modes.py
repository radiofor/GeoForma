"""Persist the interactive annotation context and its edit history."""
INDIVIDUAL='individual'


class ModeWorkflow:
    def annotation_mode(self):return INDIVIDUAL

    def annotation_context(self):return (self.project_epoch,self.image['id'] if self.image else None,self.annotation_mode())

    def capture_label_histories(self):
        from ..history import history_snapshot
        self.mode_histories[self.annotation_mode()]=(self.label_undo,self.label_redo)
        record={'scope':'all_labels','labels':{mode:{'undo':undo,'redo':redo} for mode,(undo,redo) in self.mode_histories.items()}}
        self.project['history']=history_snapshot(record)

    def restore_label_histories(self):
        from ..history import history_snapshot
        history=history_snapshot(self.project.get('history',{}))
        self.mode_histories={mode:(record['undo'],record['redo']) for mode,record in history['labels'].items()}
        self.label_undo,self.label_redo=self.mode_histories.get(self.annotation_mode(),([],[]))


    def invalidate_model_drafts(self,image_ids=None):
        """Invalidate model-refined drafts while retaining manual geometry."""
        from ..editing_state import manual_label
        labels_by_id=None
        def invalidate(draft):
            nonlocal labels_by_id
            if not draft:return
            if draft.get('editing_state')=='manual':return
            base=draft.get('base_id')
            if base:
                if labels_by_id is None:labels_by_id={label['id']:label for label in self.project['labels']}
                if manual_label(labels_by_id.get(base)):return
            draft['pending']=True;draft['ignore_seed']=True
            draft.pop('choices',None);draft.pop('logits',None)
        def affected(image_id):return image_ids is None or image_id in image_ids
        if self.image and affected(self.image['id']):invalidate(self.draft)
        for image in self.project['images']:
            if affected(image['id']):
                invalidate(image.get('mode_sessions',{}).get(INDIVIDUAL,{}).get('draft'))
        for (image_id,mode),session in self.image_sessions.items():
            if affected(image_id):invalidate(session.get('draft'))
