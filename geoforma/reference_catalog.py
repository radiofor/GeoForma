"""Reference identity, stable catalog replacement and indexed read-only matching."""
from collections import defaultdict
from pathlib import Path


def reference_stem(path):return Path(path).stem.casefold()


def reference_key(record):return record['group'].casefold(),reference_stem(record['path'])


def merge_references(existing,incoming):
    names={}
    for record in existing:names.setdefault(record['group'].casefold(),record['group'])
    updates={}
    for record in incoming:
        name=names.setdefault(record['group'].casefold(),record['group'])
        normalized=record if record['group']==name else dict(record,group=name)
        updates[reference_key(normalized)]=normalized
    result=[updates.pop(reference_key(record),record) for record in existing]
    return result+list(updates.values())


def equivalent_reference(record,choices):
    """Return the live record, never install an equal but stale UI dictionary."""
    return next((choice for choice in choices if choice is record or choice==record),None)


class ReferenceLookup:
    def __init__(self):self.source=None;self.length=-1;self.by_stem={}

    def for_image(self,references,image):
        if references is not self.source or len(references)!=self.length:
            grouped=defaultdict(list)
            for record in references:grouped[reference_stem(record['path'])].append(record)
            self.source=references;self.length=len(references);self.by_stem={key:tuple(value) for key,value in grouped.items()}
        return self.by_stem.get(reference_stem(image['path']),()) if image and image.get('path') else ()
