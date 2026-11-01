"""Deterministic native-library placement for PyInstaller, without unsafe pruning."""
from pathlib import Path
import ast,hashlib,sys

def sha256_file(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def external_standard_imports(roots):
    """Wheel Python code is external, so Analysis cannot see its stdlib imports."""
    found=set()
    for root in roots:
        for path in Path(root).rglob('*.py'):
            if 'test' in path.parts or 'tests' in path.parts:continue
            try:tree=ast.parse(path.read_text(encoding='utf-8-sig'))
            except (OSError,SyntaxError,UnicodeError):continue
            for node in ast.walk(tree):
                names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and not node.level and node.module else []
                for name in names:
                    # CPython 3.13 exposes this as an alias created by the
                    # collections package; PyInstaller cannot locate it as a
                    # separate hidden module.
                    if name=='collections.abc' and sys.version_info>=(3,13):name='collections'
                    if name.split('.')[0] in sys.stdlib_module_names and name.split('.')[0] not in ('tkinter','turtle','idlelib','test'):found.add(name)
    return sorted(found)

def deduplicate_binaries(entries):
    """Same basename AND content only. Prefer library-native dependency paths."""
    groups={};rest=[]
    for entry in entries:
        destination,source,kind=entry
        if Path(destination).suffix.lower()!='.dll':rest.append(entry);continue
        path=Path(source)
        digest=sha256_file(path)
        groups.setdefault((Path(destination).name.casefold(),digest),[]).append(entry)
    def rank(entry):
        destination=entry[0].replace('\\','/').lower()
        name=destination.rsplit('/',1)[-1]
        bootstrap=name in ('vcruntime140.dll','vcruntime140_1.dll','zlib.dll','zlib1.dll','ucrtbase.dll') or name.startswith('api-ms-win-')
        if bootstrap and '/' not in destination:return (-1,len(destination),destination)
        return (0 if destination.startswith('torch/lib/') else 1 if destination.startswith('library/bin/') else 2,len(destination),destination)
    return rest+[min(group,key=rank) for group in groups.values()]
