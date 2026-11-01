import json
from geoforma import package_context


def test_packaged_application_keeps_windows_assigned_aumid(monkeypatch):
    monkeypatch.setattr(package_context.sys,'platform','win32');calls=[]
    monkeypatch.setattr(package_context,'current_package_family',lambda:'ViktorXu.GeoForma_s2bqyvzr3155p')
    package_context.configure_application_id(calls.append);assert not calls
    monkeypatch.setattr(package_context,'current_package_family',lambda:None)
    package_context.configure_application_id(calls.append);assert calls==['GeoForma.Desktop']


def test_store_channel_is_an_explicit_resource_not_an_environment_switch(tmp_path,monkeypatch):
    monkeypatch.setattr('geoforma.distribution.resource_root',lambda:tmp_path)
    monkeypatch.setenv('GEOFORMA_BUILD_CHANNEL','store');package_context.is_store_build.cache_clear()
    try:
        assert not package_context.is_store_build()
        folder=tmp_path/'geoforma';folder.mkdir();(folder/'store-profile.json').write_text(json.dumps({'kind':'geoforma-store-profile-v1'}))
        package_context.is_store_build.cache_clear();assert package_context.is_store_build()
    finally:package_context.is_store_build.cache_clear()


def test_store_channel_uses_the_same_native_model_path(monkeypatch):
    from geoforma.execution_policy import resolve_execution
    monkeypatch.setattr(package_context,'is_store_build',lambda:True)
    monkeypatch.setattr('geoforma.execution_policy.native_available',lambda family:False)
    assert resolve_execution({'backend':'sam','variant':'vit_b','execution':'auto'})=='native'
