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


def reorder_reference_groups(records,visible_order):
    """Reorder visible types while keeping other types in their existing slots."""
    groups=list(dict.fromkeys(record['group'].casefold() for record in records))
    wanted=list(visible_order);wanted_set=set(wanted)
    current=[group for group in groups if group in wanted_set]
    if len(wanted)!=len(wanted_set) or set(current)!=wanted_set or current==wanted:return records
    replacement=iter(wanted);order=[next(replacement) if group in wanted_set else group for group in groups]
    grouped={group:[] for group in groups}
    for record in records:grouped[record['group'].casefold()].append(record)
    return [record for group in order for record in grouped[group]]


class ReferenceLookup:
    def __init__(self):self.source=None;self.length=-1;self.by_stem={}

    def for_image(self,references,image):
        if references is not self.source or len(references)!=self.length:
            grouped=defaultdict(list)
            for record in references:grouped[reference_stem(record['path'])].append(record)
            self.source=references;self.length=len(references);self.by_stem={key:tuple(value) for key,value in grouped.items()}
        return self.by_stem.get(reference_stem(image['path']),()) if image and image.get('path') else ()
