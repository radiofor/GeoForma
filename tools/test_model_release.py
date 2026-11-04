"""Validate frozen model adapters without a developer Python/PATH dependency."""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.model_catalog import MODELS
from geoforma.distribution import VERSION


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models',nargs='*');parser.add_argument('--device',default='cuda');parser.add_argument('--bundle',type=Path,default=ROOT/'release'/VERSION/'portable/GeoForma');args=parser.parse_args()
    bundle=args.bundle.resolve();out=bundle.parent.parent/'qa'/('models_final' if args.models else 'models');out.mkdir(parents=True,exist_ok=True);data=out/'data';models=data/'models';models.mkdir(parents=True,exist_ok=True)
    from geoforma.weights import default_checkpoint
    source={spec['id']:default_checkpoint(spec['variant'],spec['backend']) for spec in MODELS}
    env=dict(os.environ)
    for key in ['PYTHONPATH','PYTHONHOME','CONDA_PREFIX','CONDA_DEFAULT_ENV','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','GDAL_DATA','PROJ_DATA','PROJ_LIB','CUDA_VISIBLE_DEVICES']:env.pop(key,None)
    env.update(PATH=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot'],QT_QPA_PLATFORM='offscreen',GEOFORMA_DATA_DIR=str(data))
    exe=bundle/'GeoForma.exe';rows=[];copies=[]
    try:
        for spec in MODELS:
            if args.models and spec['id'] not in args.models:continue
            if not (bundle/'models'/spec['file']).is_file():
                target=models/spec['file']
                if not target.exists():shutil.copy2(source[spec['id']],target);copies.append(target)
            report=out/(spec['id']+'.json');start=time.monotonic()
            code=subprocess.run([str(exe),'--self-test',str(report),'--test-device',args.device,'--test-model',spec['id']],env=env,cwd=out,timeout=600).returncode
            result=json.loads(report.read_text());assert code==0 and result['ok'] and result['frozen'],result
            rows.append({'model':spec['id'],'ok':True,'device':result['device'],'seconds':round(time.monotonic()-start,2)});print(rows[-1],flush=True)
            (out/'results.json').write_text(json.dumps({'ok':True,'models':rows,'developer_environment_removed':True},indent=2))
    finally:
        for path in copies:
            if path.resolve().is_relative_to(models.resolve()):path.unlink(missing_ok=True)


if __name__=='__main__':main()
