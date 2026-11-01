"""Remove recognized, aged build/test scratch; preserve reports and releases."""
import argparse,json,os,re,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.test_scratch import remove_checked

SCOPES=('','optional_resources_qa','prestore_audit_2026_10_25','msix_1_0_0','release_1_0_0')
# Historical test-only environments and download copies; reports remain in place.
OBSOLETE=('optional_resources_qa/data','optional_resources_qa/auto-data',
          'torch210_validation',
          'security_wheels/torch-2.10.0+cu128-cp313-cp313-win_amd64.whl',
          'security_wheels/torchvision-0.25.0+cu128-cp313-cp313-win_amd64.whl')


def inventory_tree(path):
    size=files=0
    def fail(error):raise error
    for folder,children,names in os.walk(path,followlinks=False,onerror=fail):
        for name in children+names:
            child=Path(folder)/name
            if child.is_symlink() or child.is_junction():raise ValueError('目录包含链接')
        for name in names:
            file=Path(folder)/name
            if file.is_file():size+=file.stat().st_size;files+=1
    return size,files


def clean(root,*,apply=False,older_hours=24,obsolete=False,prefixes=()):
    build=(Path(root).resolve()/'build')
    if build.is_symlink() or build.is_junction() or not build.is_dir():raise ValueError('构建目录无效。')
    build=build.resolve();cutoff=time.time()-older_hours*3600
    report={'applied':apply,'older_hours':older_hours,'targets':[],'skipped':[],'bytes':0,'files':0}
    candidates=[]
    for relative in SCOPES:
        scope=build/relative
        if not scope.is_dir() or scope.is_symlink() or scope.is_junction():continue
        for path in scope.iterdir():
            if prefixes and not any(path.name.startswith(prefix) for prefix in prefixes):continue
            if path.is_symlink() or path.is_junction() or not path.is_dir():continue
            try:
                if path.stat().st_mtime>cutoff:continue
                entries=list(path.iterdir())
                if entries and all(re.fullmatch(r'test_.+\d+',entry.name) and entry.is_dir() and not entry.is_symlink() and not entry.is_junction() for entry in entries):
                    candidates.append((path,'pytest fixtures'))
            except OSError as error:report['skipped'].append({'path':path.relative_to(build).as_posix(),'reason':str(error)})
    if obsolete:
        for relative in OBSOLETE:
            path=build/relative
            if path.exists() and path.stat().st_mtime<=cutoff:candidates.append((path,'obsolete validation payload'))
    for path,reason in candidates:
        try:
            relative=path.relative_to(build);current=build
            for part in relative.parts:
                current=current/part
                if current.is_symlink() or current.is_junction():raise ValueError('清理路径包含链接')
            if not path.resolve().is_relative_to(build) or path.resolve()==build:raise ValueError('清理路径不安全')
            if path.is_dir():size,files=inventory_tree(path)
            elif path.is_file():size,files=path.stat().st_size,1
            else:continue
            if apply:
                if path.is_dir():remove_checked(build,path)
                else:path.unlink()
            report['targets'].append({'path':path.relative_to(build).as_posix(),'reason':reason,'files':files,'bytes':size})
            report['bytes']+=size;report['files']+=files
        except (OSError,ValueError) as error:report['skipped'].append({'path':path.relative_to(build).as_posix(),'reason':str(error)})
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--older-hours',type=float,default=24)
    parser.add_argument('--obsolete-payloads',action='store_true')
    parser.add_argument('--prefix',action='append',default=[],help='Restrict recognized test scratch names')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.older_hours<0:parser.error('--older-hours must be non-negative')
    if args.prefix and args.obsolete_payloads:parser.error('--prefix cannot be combined with --obsolete-payloads')
    report=clean(ROOT,apply=args.apply,older_hours=args.older_hours,obsolete=args.obsolete_payloads,prefixes=args.prefix)
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('applied','older_hours','bytes','files')}|{'targets':len(report['targets']),'skipped':len(report['skipped'])},ensure_ascii=False))
