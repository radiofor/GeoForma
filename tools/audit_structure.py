"""Repeatable source inventory; findings are review candidates, not deletion rules."""
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def inventory():
    modules=[]
    for path in sorted((ROOT/'geoforma').rglob('*.py')):
        source=path.read_text(encoding='utf-8-sig');tree=ast.parse(source)
        loaded={node.id for node in ast.walk(tree) if isinstance(node,ast.Name) and isinstance(node.ctx,ast.Load)}
        imported=[]
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                for alias in node.names:
                    if alias.name!='*':imported.append((alias.asname or alias.name.split('.')[0],node.lineno))
        modules.append({'path':path.relative_to(ROOT).as_posix(),'lines':len(source.splitlines()),
            'functions':sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree)),
            'unused_import_candidates':[(name,line) for name,line in imported if name not in loaded and name!='annotations']})
    return {'modules':len(modules),'lines':sum(m['lines'] for m in modules),'files':modules}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=inventory()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'modules':report['modules'],'lines':report['lines'],
        'largest':sorted(report['files'],key=lambda m:m['lines'],reverse=True)[:8],
        'unused_import_candidates':{m['path']:m['unused_import_candidates'] for m in report['files'] if m['unused_import_candidates']}}))
