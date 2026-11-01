"""Real frozen optional-runtime acceptance, using isolated resource data only."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--weight',type=Path,help='Existing official SAM 2.1 Small checkpoint for the install phase');parser.add_argument('--torch-wheel',type=Path,help='Existing GPU PyTorch wheel outside the isolated data directory');parser.add_argument('--phase',choices=['core','install','inference','cpu-auto','cpu-runtime'],required=True);args=parser.parse_args()
    if args.phase=='install' and (args.weight is None or not args.weight.is_file()):parser.error('install phase requires --weight with an existing official checkpoint')
    if args.torch_wheel is not None and not args.torch_wheel.is_file():parser.error('--torch-wheel must be an existing file')
    from geoforma.native_runtime import catalog
    from geoforma.atomic_io import read_json,atomic_json
    bundle=args.bundle.resolve();data=args.data.resolve();qa=data.parent/'frozen-qa';qa.mkdir(parents=True,exist_ok=True)
    executable=bundle/'GeoForma.exe';env=dict(os.environ,GEOFORMA_DATA_DIR=str(data),GEOFORMA_SETTINGS_FILE=str(data/'test.ini'),QT_QPA_PLATFORM='offscreen')
    env['PATH']=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot']
    for key in ('PYTHONPATH','PYTHONHOME','CONDA_PREFIX','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','GDAL_DATA','PROJ_DATA','PROJ_LIB'):env.pop(key,None)
    def run(name,arguments,environment=env,timeout=240):
        output=qa/(name+'.json');output.unlink(missing_ok=True);start=time.monotonic()
        flag='--self-test' if name.startswith(('inference_','core_')) else '--output'
        command=[str(executable),*arguments,flag,str(output)]
        result=subprocess.run(command,env=environment,cwd=ROOT,capture_output=True,timeout=timeout)
        report=read_json(output) if output.exists() else dict(ok=False,error=result.stderr.decode(errors='replace'))
        if result.returncode or not report['ok']:raise RuntimeError(name+' failed: '+report.get('error','')[-4000:])
        print(name,'PASSED',round(time.monotonic()-start,2),flush=True);return report
    if args.phase=='core':
        import shutil
        for scale in ('1','1.5'):
            report=run('core_'+scale,['--test-core-only'],dict(env,GEOFORMA_DATA_DIR=str(data.parent/'empty-data'),QT_SCALE_FACTOR=scale),timeout=60)
            assert report['resources']=={'runtime':False,'weight':False}
            shutil.copy2(qa/'resource_setup.png',qa/('core_'+scale+'.png'))
    elif args.phase=='install':
        empty=run('missing_runtime',['--resource-command','status'],dict(env,GEOFORMA_DATA_DIR=str(data.parent/'empty-data')))
        assert not empty['result']['ready']
        profile='cu126';wheels=[str(args.torch_wheel.resolve())] if args.torch_wheel else [str(data/'runtime/native-v1/downloads'/w['filename']) for w in catalog()['profiles'][profile]['wheels'] if w['name']=='torch']
        run('runtime_local',['--resource-command','install-runtime','--resource-profile',profile,'--resource-files',*wheels],timeout=900)
        run('weight_local',['--resource-command','install-weight','--resource-model','sam2.1_small','--resource-files',str(args.weight.resolve())])
    elif args.phase=='inference':
        cpu=run('inference_cpu',['--test-device','cpu'])
        gpu=run('inference_cuda',['--test-device','cuda'])
        fallback=run('inference_fallback',['--test-device','cuda'],dict(env,CUDA_VISIBLE_DEVICES='-1'))
        assert cpu['device']=='cpu' and gpu['device']=='cuda' and fallback['device']=='cpu'
        atomic_json(qa/'summary.json',dict(ok=True,tests=['cpu','cuda','cpu_fallback'],optional_runtime=True),indent=2)
    elif args.phase=='cpu-auto':
        result=run('runtime_cpu_auto',['--resource-command','install-runtime','--resource-profile','cpu'],timeout=900)
        assert result['result']['profile']=='cpu' and any('下载 torch' in item['text'] for item in result['progress'])
    else:
        wheels=[str(data/'runtime/native-v1/downloads'/w['filename']) for w in catalog()['profiles']['cpu']['wheels'] if w['name']=='torch']
        run('runtime_cpu_only',['--resource-command','install-runtime','--resource-profile','cpu','--resource-files',*wheels])
        cpu=run('inference_cpu_only',['--test-device','cpu'])
        fallback=run('inference_cpu_only_fallback',['--test-device','cuda'])
        assert cpu['device']==fallback['device']=='cpu'
        atomic_json(qa/'cpu_only_summary.json',dict(ok=True,tests=['cpu_runtime_install','cpu_inference','cpu_runtime_gpu_preference_fallback']),indent=2)

if __name__=='__main__':main()
