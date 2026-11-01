from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
import pytest
from geoforma.atomic_io import read_json
from geoforma.msix_package import publisher_id,validate_identity,package_version,manifest_bytes,file_mapping,FOUNDATION,UAP10,RESCAP


def profile():return read_json(Path(__file__).resolve().parents[1]/'packaging/store-profile.json')


def test_store_identity_matches_independent_publisher_family_and_manifest():
    data=profile()
    assert publisher_id('CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US')=='8wekyb3d8bbwe'
    assert validate_identity(data)=='ViktorXu.GeoForma_s2bqyvzr3155p'
    root=ET.fromstring(manifest_bytes(data,'1.0.0'));identity=root.find('{'+FOUNDATION+'}Identity')
    assert identity.get('Name')==data['identity_name'] and identity.get('Publisher')==data['publisher'] and identity.get('Version')=='1.0.0.0'
    app=root.find('{'+FOUNDATION+'}Applications/{'+FOUNDATION+'}Application')
    assert app.get('{'+UAP10+'}RuntimeBehavior')=='win32App' and app.get('{'+UAP10+'}TrustLevel')=='mediumIL'
    assert [node.get('Name') for node in root.findall('{'+FOUNDATION+'}Capabilities/{'+RESCAP+'}Capability')]==['runFullTrust']
    with pytest.raises(ValueError):validate_identity(dict(data,publisher='CN=Other Publisher'))


@pytest.mark.parametrize('version',['0.1.0','1.0','1.0.0.1','1.65536.0','1.x.0'])
def test_store_version_keeps_fourth_component_reserved(version):
    with pytest.raises(ValueError):package_version(version)


def test_four_part_application_version_is_not_extended():
    assert package_version('1.0.1.0')=='1.0.1.0'


@pytest.mark.parametrize('destination',['../escape.dll',r'\escape.dll',r'C:\escape.dll','App/module.dll:stream','App/中文.dll'])
def test_mapping_rejects_escaped_or_nonportable_destinations(tmp_path,destination):
    source=tmp_path/'input.dll';source.write_bytes(b'input')
    with pytest.raises(ValueError):file_mapping([(source,destination)])


def test_mapping_preserves_spaces_and_rejects_case_collisions(tmp_path):
    source=tmp_path/'file with spaces.dll';source.write_bytes(b'input')
    result=file_mapping([(source,'App/module.dll')])
    assert result.startswith('[Files]\n"') and '"App\\module.dll"' in result
    with pytest.raises(ValueError):file_mapping([(source,'App/module.dll'),(source,'app/MODULE.dll')])


def test_packaged_payload_matches_every_inventory_entry(tmp_path):
    from tools.build_msix import verify_archived_payload
    bundle=tmp_path/'bundle';bundle.mkdir()
    (bundle/'release-manifest.json').write_text(json.dumps({'version':'1.0.3'}),encoding='utf-8')
    content=b'original';records=[{'path':'GeoForma.exe','bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}]
    package=tmp_path/'test.msix'
    def write(executable=content,extra=False):
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('App/GeoForma.exe',executable)
            archive.write(bundle/'release-manifest.json','App/release-manifest.json')
            if extra:archive.writestr('App/unlisted.dll',b'extra')
    write()
    with zipfile.ZipFile(package) as archive:assert verify_archived_payload(archive,bundle,records)==2
    write(b'changed!')
    with zipfile.ZipFile(package) as archive,pytest.raises(ValueError,match='内容校验失败'):
        verify_archived_payload(archive,bundle,records)
    write(extra=True)
    with zipfile.ZipFile(package) as archive,pytest.raises(ValueError,match='清单不一致'):
        verify_archived_payload(archive,bundle,records)


def test_packaged_payload_decodes_opc_part_names_and_rejects_duplicates(tmp_path):
    from tools.build_msix import verify_archived_payload
    bundle=tmp_path/'bundle';bundle.mkdir()
    (bundle/'release-manifest.json').write_text('{}',encoding='utf-8')
    content=b'wheel';records=[{'path':'runtime/torch+cpu 1.whl','bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}]
    package=tmp_path/'test.msix'
    def write(duplicate=False):
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('App/runtime/torch%2Bcpu%201.whl',content)
            archive.write(bundle/'release-manifest.json','App/release-manifest.json')
            if duplicate:archive.writestr('App/runtime/torch+cpu 1.whl',content)
    write()
    with zipfile.ZipFile(package) as archive:assert verify_archived_payload(archive,bundle,records)==2
    write(duplicate=True)
    with zipfile.ZipFile(package) as archive,pytest.raises(ValueError,match='清单不一致'):
        verify_archived_payload(archive,bundle,records)
