"""Native distribution resources and safe cache cleanup."""
from types import SimpleNamespace
from pathlib import Path
import json
import pytest


def test_cache_cleanup_preserves_projects_models_and_unknown_files(tmp_path,monkeypatch):
    from geoforma import cache_commands
    monkeypatch.setattr(cache_commands,'data_dir',lambda:tmp_path)
    for name in ['cache/features','models','recovery']:(tmp_path/name).mkdir(parents=True)
    feature=tmp_path/'cache/features'/('a'*64+'.pt');feature.write_bytes(b'feature')
    image=tmp_path/'cache/features/image.tif';image.write_bytes(b'original')
    model=tmp_path/'models/model.pth';model.write_bytes(b'model');recovery=tmp_path/'recovery/project.json';recovery.write_text('project')
    report=tmp_path/'cleanup.json'
    assert cache_commands.cleanup_command(report)==0 and json.loads(report.read_text())['ok']
    assert not feature.exists() and image.exists() and model.exists() and recovery.exists()


def test_offline_checkpoint_is_preferred_without_a_download(tmp_path,monkeypatch):
    import geoforma.distribution as distribution
    from geoforma.weights import default_checkpoint,ensure_checkpoint
    monkeypatch.setattr(distribution,'bundled_checkpoint',distribution.bundled_checkpoint.__wrapped__)
    bundle=tmp_path/'app';(bundle/'models').mkdir(parents=True);weight=bundle/'models/sam_vit_b_01ec64.pth';weight.write_bytes(b'packaged')
    monkeypatch.setattr(distribution,'install_root',lambda:bundle);monkeypatch.setattr(distribution,'resource_root',lambda:bundle)
    assert default_checkpoint('vit_b')==weight
    task=SimpleNamespace(check=lambda:pytest.fail('Must not download bundled weight'))
    assert ensure_checkpoint({'variant':'vit_b','checkpoint':str(tmp_path/'missing.pth')},task)==str(weight)


def test_release_rejects_old_executable_or_extra_runtime_payload(tmp_path):
    from tools.build_release import require_native_release
    version='1.0.2.0'
    require_native_release(tmp_path,{'version':version,'execution':'native'},version)
    with pytest.raises(ValueError,match='完整重新构建'):
        require_native_release(tmp_path,{'version':version},version)
    (tmp_path/'runtime').mkdir()
    with pytest.raises(ValueError,match='完整重新构建'):
        require_native_release(tmp_path,{'version':version,'execution':'native'},version)


def test_release_fails_before_writing_when_dependencies_conflict(tmp_path,monkeypatch):
    from tools import build_release,check_dependencies
    monkeypatch.setattr('geoforma.runtime_profile.activate_security_profile',lambda root:None)
    monkeypatch.setattr('geoforma.runtime_profile.require_release_security',lambda:None)
    monkeypatch.setattr(check_dependencies,'require_consistent_dependencies',lambda:(_ for _ in ()).throw(ValueError('依赖不一致')))
    output=tmp_path/'release'
    monkeypatch.setattr('sys.argv',['build_release.py','--optional-runtime','--output-dir',str(output)])
    with pytest.raises(ValueError,match='依赖不一致'):build_release.main()
    assert not output.exists()


@pytest.mark.parametrize('mode,expected',[
    ('optional',['frozen_core']),('bundled',['frozen_cpu','frozen_cuda','frozen_cpu_fallback']),
])
def test_release_native_qa_matches_runtime_packaging(tmp_path,monkeypatch,mode,expected):
    import sys
    from geoforma.distribution import VERSION
    from tools import test_release
    bundle=tmp_path/'release'/'portable'/'GeoForma';bundle.mkdir(parents=True)
    (bundle/'release-manifest.json').write_text(json.dumps({'version':VERSION,'runtime_mode':mode}),encoding='utf-8')
    (bundle/'GeoForma.exe').write_bytes(b'fake');calls=[]
    def run(command,env,cwd,timeout):
        report=Path(command[command.index('--self-test')+1]);name=report.stem;calls.append((name,command))
        result={'ok':True,'frozen':True,'version':VERSION,'qt_plugins':str(bundle/'plugins')}
        if '--test-core-only' not in command:
            result['model']={'checkpoint':str(bundle/'models'/'weight.pt')}
            result['device']='cpu' if env.get('CUDA_VISIBLE_DEVICES')=='-1' else command[command.index('--test-device')+1]
        report.write_text(json.dumps(result),encoding='utf-8')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(test_release.subprocess,'run',run)
    monkeypatch.setattr(sys,'argv',['test_release.py','--phase','native','--bundle',str(bundle)])
    test_release.main()
    assert [name for name,_ in calls]==expected
    assert all(('--test-core-only' in command)==(mode=='optional') for _,command in calls)


def test_release_relocation_cleans_owned_temporary_directory_when_copy_fails(tmp_path,monkeypatch):
    import sys
    from tools import test_release
    bundle=tmp_path/'release'/'portable'/'GeoForma';bundle.mkdir(parents=True)
    (bundle/'release-manifest.json').write_text(json.dumps({'version':'test','runtime_mode':'optional'}),encoding='utf-8')
    temporary=tmp_path/'geoforma_路径测试';temporary.mkdir()
    monkeypatch.setattr(test_release.tempfile,'mkdtemp',lambda **kwargs:str(temporary))
    monkeypatch.setattr(test_release.tempfile,'gettempdir',lambda:str(tmp_path))
    monkeypatch.setattr(test_release.shutil,'copytree',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('copy failed')))
    monkeypatch.setattr(sys,'argv',['test_release.py','--phase','relocated','--bundle',str(bundle)])
    with pytest.raises(OSError,match='copy failed'):test_release.main()
    assert bundle.exists() and not temporary.exists()


def test_bundled_release_ignores_older_managed_runtime(monkeypatch):
    from geoforma import native_runtime,execution_policy
    monkeypatch.setattr(native_runtime,'bundled_release',lambda:True)
    monkeypatch.setattr(native_runtime,'lightweight',lambda:False)
    monkeypatch.setattr(native_runtime,'managed_runtime',lambda:pytest.fail('must not use older managed runtime'))
    monkeypatch.setattr(execution_policy,'find_spec',lambda name:object())
    assert native_runtime.activate() is None
    assert native_runtime.status()['source']=='bundled'
    assert execution_policy.native_available('sam2')


def test_bundled_release_rejects_mismatched_cuda_runtime_before_writing(tmp_path,monkeypatch):
    from tools import build_release,check_dependencies
    monkeypatch.setattr('geoforma.runtime_profile.activate_security_profile',lambda root:None)
    monkeypatch.setattr('geoforma.runtime_profile.require_release_security',lambda:None)
    monkeypatch.setattr(check_dependencies,'require_consistent_dependencies',lambda:None)
    monkeypatch.setattr(build_release.importlib.metadata,'version',lambda name:'2.13.0+cpu')
    output=tmp_path/'release'
    monkeypatch.setattr('sys.argv',['build_release.py','--bundled-runtime-no-weights','--output-dir',str(output)])
    with pytest.raises(ValueError,match='NVIDIA CUDA'):build_release.main()
    assert not output.exists()
