"""Remove only reproducible source/test caches; never traverse release, data or models."""
import argparse,json,os,shutil
from pathlib import Path

SCOPES=('geoforma','tests','tools','packaging')


def cache_paths(root):
    root=Path(root).resolve();result=[]
    def safe(path,scope):
        return not path.is_symlink() and not path.is_junction() and path.resolve().is_relative_to(scope.resolve())
    for name in ('__pycache__','.pytest_cache'):
        path=root/name
        if path.is_dir() and safe(path,root):result.append(path)
    for name in SCOPES:
        scope=root/name
        if not scope.is_dir() or not safe(scope,root):continue
        for directory,children,_ in os.walk(scope,followlinks=False):
            children[:]=[name for name in children if safe(Path(directory)/name,scope)]
            if '__pycache__' in children:
                result.append(Path(directory)/'__pycache__');children.remove('__pycache__')
    return result


def clean(root,apply=False):
    root=Path(root).resolve();report={'applied':apply,'directories':[],'skipped_links':[],'bytes':0,'files':0}
    for path in cache_paths(root):
        resolved=path.resolve()
        # Resolve and recheck each exact target immediately before recursive removal.
        if resolved==root or not resolved.is_relative_to(root) or path.is_symlink() or path.is_junction():raise ValueError('清理路径不安全。')
        files=[];links=[]
        for directory,children,names in os.walk(path,followlinks=False):
            for name in list(children):
                child=Path(directory)/name
                if child.is_symlink() or child.is_junction():links.append(child);children.remove(name)
            for name in names:
                file=Path(directory)/name
                if file.is_symlink():links.append(file)
                elif file.is_file():files.append(file)
        if links:report['skipped_links'].append(path.relative_to(root).as_posix());continue
        report['directories'].append(path.relative_to(root).as_posix());report['files']+=len(files);report['bytes']+=sum(file.stat().st_size for file in files)
        if apply:shutil.rmtree(path)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=clean(Path(__file__).resolve().parents[1],args.apply)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
