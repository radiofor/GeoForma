"""Read-only lookups over immutable label records, rebuilt after collection changes."""
from collections import defaultdict


class LabelLookup:
    def __init__(self):self.source=None;self.length=-1;self.by_image={};self.by_id={}

    def clear(self):self.source=None;self.length=-1;self.by_image.clear();self.by_id.clear()

    def for_image(self,labels,image_id):
        if labels is not self.source or len(labels)!=self.length:
            grouped=defaultdict(list)
            for label in labels:grouped[label['image_id']].append(label)
            self.source=labels;self.length=len(labels);self.by_image={key:tuple(value) for key,value in grouped.items()}
            self.by_id={label['id']:label for label in labels}
        return self.by_image.get(image_id,())

    def for_id(self,labels,image_id,identifier):
        self.for_image(labels,image_id);label=self.by_id.get(identifier)
        return label if label and label['image_id']==image_id else None
