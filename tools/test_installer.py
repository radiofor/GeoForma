"""Install/uninstall in a private directory; preserve every pre-existing distro."""
import argparse,json,os,subprocess,sys,winreg
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoforma.distribution import VERSION

KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E9A728A8-9D4C-49B7-AC67-A6372D7B4E0D}_is1'
def installed():
    return bool(install_locations())

def install_locations():
    locations=[]
    for hive,view in ((winreg.HKEY_CURRENT_USER,0),(winreg.HKEY_LOCAL_MACHINE,winreg.KEY_WOW64_32KEY),(winreg.HKEY_LOCAL_MACHINE,winreg.KEY_WOW64_64KEY)):
        try:
            with winreg.OpenKey(hive,KEY,0,winreg.KEY_READ|view) as key:locations.append(Path(winreg.QueryValueEx(key,'InstallLocation')[0]).resolve())
        except FileNotFoundError:pass
    return locations

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--installer',type=Path,default=ROOT/'release'/VERSION/'installer'/('GeoForma-'+VERSION+'-win64-setup.exe'));parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    qa=args.installer.resolve().parent.parent/'qa';destination=qa/'installed/GeoForma';data=qa/'install-data';data.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env.update(GEOFORMA_DATA_DIR=str(data),GEOFORMA_SETTINGS_FILE=str(data/'application.ini'),QT_QPA_PLATFORM='offscreen',PATH=os.environ['SystemRoot']+'/System32;'+os.environ['SystemRoot'])
    for key in ['PYTHONPATH','PYTHONHOME','CONDA_PREFIX','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','GDAL_DATA','PROJ_DATA','PROJ_LIB']:env.pop(key,None)
    results={}
    if installed():
        if not args.resume or install_locations()!=[destination.resolve()]:raise RuntimeError('An existing GeoForma installation must not be overwritten by this test')
    else:subprocess.run([str(args.installer.resolve()),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=','/GROUP=GeoForma Packaging Test','/DIR='+str(destination),'/LOG='+str(qa/'install.log')],env=env,check=True,timeout=900)
    assert installed() and (destination/'GeoForma.exe').exists()
    manifest=json.loads((destination/'release-manifest.json').read_text(encoding='utf-8'))
    optional=manifest.get('runtime_mode')=='optional'
    assert manifest['version']==VERSION and (optional or (destination/manifest['default_model']['file']).is_file())
    assert manifest.get('execution','native')=='native' and not (destination/'runtime').exists()
    results.update(offline_dependencies_installed=True,execution='native')
    report=qa/'installed-self-test.json';subprocess.run([str(destination/'GeoForma.exe'),'--self-test',str(report),*(['--test-core-only'] if optional else [])],env=env,check=True,timeout=300)
    assert json.loads(report.read_text())['ok'];results['installed_core_self_test' if optional else 'installed_offline_self_test']=True
    project=destination/'retained.gfm';project.write_text('user project')
    recovery=data/'recovery/project.gfm';recovery.parent.mkdir(exist_ok=True);recovery.write_text('recovery')
    model=data/'models/user_model.pth';model.parent.mkdir(exist_ok=True);model.write_bytes(b'user model')
    feature=data/'cache/features'/('a'*64+'.pt');feature.parent.mkdir(parents=True,exist_ok=True);feature.write_bytes(b'cached')
    uninstall=next(destination.glob('unins*.exe'));subprocess.run([str(uninstall),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(qa/'uninstall.log')],env=env,check=True,timeout=600)
    assert not installed() and not (destination/'GeoForma.exe').exists();assert project.exists() and recovery.exists() and model.exists() and feature.exists()
    results.update(uninstall=True,user_data_preserved=True,ok=True)
    (qa/'installer_results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2),flush=True)

if __name__=='__main__':main()
