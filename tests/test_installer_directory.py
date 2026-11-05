"""Exercise the real Inno Setup path normalization without installing anything."""
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
ISCC=ROOT/'environment/build-tools/inno/ISCC.exe'


@pytest.mark.skipif(sys.platform!='win32' or not ISCC.is_file(),reason='Inno Setup compiler unavailable')
def test_installer_normalizes_selected_directory(tmp_path):
    bundle=tmp_path/'bundle';bundle.mkdir();(bundle/'check.txt').write_text('test',encoding='utf-8')
    output=tmp_path/'output';output.mkdir();report=tmp_path/'result.txt'
    source=(ROOT/'packaging/geoforma.iss').read_text(encoding='utf-8')
    source=source.replace('PrivilegesRequired=admin','PrivilegesRequired=lowest')
    source=source.replace('AppId={{E9A728A8-9D4C-49B7-AC67-A6372D7B4E0D}',
                          'AppId={{AD05B1B8-73BB-4F19-8F6E-C5BCF1509814}')
    source=source.replace('SetupIconFile=..\\assets\\geoforma_map_pen.ico',f'SetupIconFile={ROOT / "assets/geoforma_map_pen.ico"}')
    source=source.replace('MessagesFile: "ChineseSimplified.isl"',f'MessagesFile: "{ROOT / "packaging/ChineseSimplified.isl"}"')
    source=source.replace('Source: "silent-upgrade-marker.txt"',f'Source: "{ROOT / "packaging/silent-upgrade-marker.txt"}"')
    source+='''
procedure AssertDirectory(const Input, Expected: String);
begin
  if CompareText(InstallDirectory(Input), Expected) <> 0 then
    RaiseException('Unexpected directory: ' + Input + ' -> ' + InstallDirectory(Input));
end;

function InitializeSetup: Boolean;
begin
  AssertDirectory('F:', 'F:\\GeoForma');
  AssertDirectory('F:\\', 'F:\\GeoForma');
  AssertDirectory('F:/Data', 'F:\\Data\\GeoForma');
  AssertDirectory('F:\\Data\\GeoForma\\', 'F:\\Data\\GeoForma');
  AssertDirectory('F:\\Data\\GeoForma\\GeoForma', 'F:\\Data\\GeoForma');
  AssertDirectory('C:\\Program Files\\GeoForma', 'C:\\Program Files\\GeoForma');
  AssertDirectory('relative', 'relative');
  SaveStringToFile('{report}', 'OK', False);
  Result := False;
end;
'''.replace('{report}',str(report))
    script=tmp_path/'check.iss';script.write_text(source,encoding='utf-8')
    subprocess.run([str(ISCC),'/DAppVersion=1.0.5',f'/DBundleDir={bundle}',f'/DInstallerDir={output}',
                    '/DOptionalRuntime=1',str(script)],check=True,capture_output=True,timeout=60)
    executable=output/'GeoForma-1.0.5-win64-setup.exe'
    run=subprocess.run([str(executable),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],timeout=30)
    assert run.returncode==1 and report.read_text(encoding='utf-8')=='OK'
