"""Exercise the frozen app in clean environments and a relocated Unicode path."""
import argparse,json,os,shutil,subprocess,sys,time,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from geoforma.distribution import VERSION

def restore_bundle(hidden,bundle):
    if hidden.parent.resolve()!=bundle.parent.resolve() or bundle.exists():raise ValueError('Unsafe bundle restoration')
    # Windows indexing/AV can retain a short directory handle after an EXE exits.
    # Keep the release recoverable and retry only this verified QA rename.
    for attempt in range(30):
        try:hidden.rename(bundle);return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.2)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,default=ROOT/'release'/VERSION/'portable/GeoForma');parser.add_argument('--phase',choices=['all','native','relocated'],default='all');args=parser.parse_args()
    bundle=args.bundle.resolve();qa=bundle.parent.parent/'qa';qa.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((bundle/'release-manifest.json').read_text(encoding='utf-8'))
    environment=dict(os.environ)
    for key in ['PYTHONPATH','PYTHONHOME','CONDA_PREFIX','CONDA_DEFAULT_ENV','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','GDAL_DATA','PROJ_DATA','PROJ_LIB','CUDA_VISIBLE_DEVICES']:
        environment.pop(key,None)
    environment['PATH']=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot'];environment['QT_QPA_PLATFORM']='offscreen'
    tests=[]
    def check(name,location,device='cpu',force_cpu=False):
        env=dict(environment);env['GEOFORMA_DATA_DIR']=str(qa/'native-data')
        if force_cpu:env['CUDA_VISIBLE_DEVICES']='-1'
        report=qa/(name+'.json');started=time.monotonic()
        code=subprocess.run([str(location/'GeoForma.exe'),'--self-test',str(report),'--test-device',device],env=env,cwd=qa,timeout=600).returncode
        result=json.loads(report.read_text(encoding='utf-8'));assert code==0 and result['ok'],result
        assert result['frozen'] and result['version']==manifest['version'],result
        assert Path(result['model']['checkpoint']).resolve().is_relative_to(location/'models'),result
        assert Path(result['qt_plugins']).resolve().is_relative_to(location),result
        if force_cpu:assert result['device']=='cpu'
        elif device=='cuda':assert result['device']=='cuda'
        tests.append({'name':name,'seconds':round(time.monotonic()-started,2),'ok':True,'device':result['device']});print(name,tests[-1],flush=True)
    if args.phase!='relocated':
        check('frozen_cpu',bundle);check('frozen_cuda',bundle,'cuda');check('frozen_cpu_fallback',bundle,'cuda',force_cpu=True)
    if args.phase=='native':
        (qa/'frozen_native_summary.json').write_text(json.dumps({'ok':True,'tests':tests,'developer_environment_removed':True},indent=2),encoding='utf-8');return
    temporary=Path(tempfile.mkdtemp(prefix='geoforma_路径测试 ')).resolve();(temporary/'qa-owner.txt').write_text('GeoForma release QA');moved=temporary/'GeoForma'
    if not moved.exists():
        def link(source,target):
            try:os.link(source,target)
            except OSError:shutil.copy2(source,target)
        shutil.copytree(bundle,moved,copy_function=link,ignore=shutil.ignore_patterns('runtime'))
    hidden=bundle.with_name('GeoForma_hidden_for_qa')
    if hidden.exists():raise ValueError('A prior migration test has not been restored')
    bundle.rename(hidden)
    try:
        check('frozen_relocated',moved)
    finally:
        restore_bundle(hidden,bundle)
        if temporary.parent==Path(tempfile.gettempdir()).resolve() and (temporary/'qa-owner.txt').read_text()=='GeoForma release QA':shutil.rmtree(temporary)
    (qa/('frozen_summary.json' if args.phase=='all' else 'frozen_relocated_summary.json')).write_text(json.dumps({'ok':True,'tests':tests,'developer_environment_removed':True,'original_bundle_hidden_during_relocation':True},indent=2),encoding='utf-8')

if __name__=='__main__':main()
