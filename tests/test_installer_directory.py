"""Exercise the real Inno Setup path normalization without installing anything."""
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
ISCC=ROOT/'environment/build-tools/inno/ISCC.exe'


pytestmark=pytest.mark.skipif(sys.platform!='win32' or not ISCC.is_file(),reason='Inno Setup compiler unavailable')


def compile_test_setup(tmp_path,modify):
    bundle=tmp_path/'bundle';bundle.mkdir();(bundle/'check.txt').write_text('test',encoding='utf-8')
    output=tmp_path/'output';output.mkdir();report=tmp_path/'result.txt'
    source=(ROOT/'packaging/geoforma.iss').read_text(encoding='utf-8')
    source=source.replace('PrivilegesRequired=admin','PrivilegesRequired=lowest')
    source=source.replace('AppId={{E9A728A8-9D4C-49B7-AC67-A6372D7B4E0D}',
                          'AppId={{AD05B1B8-73BB-4F19-8F6E-C5BCF1509814}')
    source=source.replace('SetupIconFile=..\\assets\\geoforma_map_pen.ico',f'SetupIconFile={ROOT / "assets/geoforma_map_pen.ico"}')
    source=source.replace('MessagesFile: "ChineseSimplified.isl"',f'MessagesFile: "{ROOT / "packaging/ChineseSimplified.isl"}"')
    source=source.replace('Source: "silent-upgrade-marker.txt"',f'Source: "{ROOT / "packaging/silent-upgrade-marker.txt"}"')
    source=modify(source,report)
    script=tmp_path/'check.iss';script.write_text(source,encoding='utf-8')
    subprocess.run([str(ISCC),'/DAppVersion=1.0.5',f'/DBundleDir={bundle}',f'/DInstallerDir={output}',
                    '/DOptionalRuntime=1',str(script)],check=True,capture_output=True,timeout=60)
    return output/'GeoForma-1.0.5-win64-setup.exe',report


def test_installer_normalizes_selected_directory(tmp_path):
    def modify(source,report):
        return source+'''
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
    executable,report=compile_test_setup(tmp_path,modify)
    run=subprocess.run([str(executable),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],timeout=30)
    assert run.returncode==1 and report.read_text(encoding='utf-8')=='OK'


@pytest.mark.parametrize('selection',['folder','drive_root','bare_drive','existing_name'])
def test_wizard_normalizes_directory_before_installation(tmp_path,selection):
    def modify(source,report):
        before="""  if CurPageID = wpSelectDir then
    WizardForm.DirEdit.Text := InstallDirectory(WizardForm.DirEdit.Text);"""
        after="""  if CurPageID = wpSelectDir then begin
    WizardForm.DirEdit.Text := InstallDirectory(WizardForm.DirEdit.Text);
    SaveStringToFile('{report}', WizardForm.DirEdit.Text, False);
    Result := False;
  end;""".replace('{report}',str(report))
        assert before in source
        return source.replace(before,after)
    executable,report=compile_test_setup(tmp_path,modify)
    choices={'folder':(str(tmp_path),str(tmp_path/'GeoForma')),
             'drive_root':('F:\\','F:\\GeoForma'),
             'bare_drive':('F:','F:\\GeoForma'),
             'existing_name':(str(tmp_path/'GeoForma'),str(tmp_path/'GeoForma'))}
    selected,expected=choices[selection]
    run=subprocess.run([str(executable),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/DIR={selected}'],timeout=30)
    assert run.returncode==1 and report.read_text(encoding='utf-8')==expected


def test_next_button_normalizes_typed_drive_before_native_validation(tmp_path):
    def modify(source,report):
        before="""  if CurPageID = wpSelectDir then
    WizardForm.DirEdit.Text := InstallDirectory(WizardForm.DirEdit.Text);"""
        after="""  if CurPageID = wpSelectDir then begin
    SaveStringToFile('{report}', WizardForm.DirEdit.Text, False);
    Result := False;
  end;""".replace('{report}',str(report))
        assert before in source
        source=source.replace(before,after)
        return source+'''
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then begin
    WizardForm.DirEdit.Text := 'F:';
    WizardForm.NextButton.OnClick(WizardForm.NextButton);
  end;
end;
'''
    executable,report=compile_test_setup(tmp_path,modify)
    run=subprocess.run([str(executable),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],timeout=30)
    assert run.returncode==1 and report.read_text(encoding='utf-8')=='F:\\GeoForma'


@pytest.mark.parametrize('scenario',['valid','default_location','bad_marker','bad_command','uninstall_failed'])
def test_cross_directory_upgrade_validates_and_uses_original_user(tmp_path,scenario):
    old=tmp_path/'prior custom location';old.mkdir()
    (old/'unins000.exe').write_bytes(b'test uninstaller is never executed')
    marker='invalid' if scenario=='bad_marker' else 'GeoForma-1.0.5-silent-uninstall-preserves-data-v1'
    (old/'silent-upgrade-marker.txt').write_text(marker,encoding='utf-8')
    def quoted(value):return str(value).replace("'","''")
    def modify(source,report):
        source=source.replace('RegKeyExists(', 'TestRegKeyExists(').replace('RegQueryStringValue(', 'TestRegQueryStringValue(')
        source=source.replace("CheckForMutexes('Local\\GeoForma.Desktop')",'False')
        source=source.replace('if WizardSilent then begin','if False then begin')
        source=source.replace("ShellExecAsOriginalUser('open', Expected,", "TestShellExec('open', Expected,")
        if scenario=='default_location':
            source=source.replace("CompareText(Location, ExpandConstant('{autopf}\\GeoForma')) = 0",
                                  "CompareText(Location, '{old}') = 0".replace('{old}',quoted(old)))
            source=source.replace('RunUninstallerWithProgress(Expected, ExitCode)',
                                  'TestRunUninstaller(Expected, ExitCode)')
        mock='''
var TestPresent, TestCalled: Boolean;
function TestRegKeyExists(RootKey: Integer; const Key: String): Boolean;
begin
  Result := TestPresent and (RootKey = HKLM64);
end;
function TestRegQueryStringValue(RootKey: Integer; const Key, Name: String; var Value: String): Boolean;
begin
  Result := True;
  if Name = 'InstallLocation' then Value := '{old}'
  else if Name = 'UninstallString' then Value := '"{old}\\unins000.exe"{suffix}'
  else if Name = 'DisplayVersion' then Value := '1.0.5'
  else Result := False;
end;
function TestShellExec(const Verb, Filename, Params, WorkingDir: String; Show: Integer;
  Wait: TExecWait; var ExitCode: Integer): Boolean;
begin
  if (Verb <> 'open') or (CompareText(Filename, '{old}\\unins000.exe') <> 0) or
     (Params <> '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART') or
     (Wait <> ewWaitUntilTerminated) then RaiseException('Unexpected uninstaller call');
  TestCalled := True;
  ExitCode := {code};
  if ExitCode = 0 then TestPresent := False;
  Result := True;
end;
function TestRunUninstaller(const Filename: String; var ExitCode: Integer): Boolean;
begin
  Result := TestShellExec('open', Filename, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
    '', SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode);
end;
'''.replace('{old}',quoted(old)).replace('{suffix}',' /unexpected' if scenario=='bad_command' else '').replace('{code}','1' if scenario=='uninstall_failed' else '0')
        source=source.replace('function PrepareToInstall(var NeedsRestart: Boolean): String;\nvar',
                              mock+'\nfunction PrepareToInstall(var NeedsRestart: Boolean): String;\nvar')
        source=source.replace('function NextButtonClick(CurPageID: Integer): Boolean;',
                              'function PrepareToInstall(var NeedsRestart: Boolean): String; forward;\n\nfunction NextButtonClick(CurPageID: Integer): Boolean;')
        source=source.replace('function NextButtonClick(CurPageID: Integer): Boolean;\nbegin\n  Result := True;',
                              '''function NextButtonClick(CurPageID: Integer): Boolean;
var Message: String; NeedsRestart: Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then begin
    TestPresent := True; TestCalled := False; NeedsRestart := False;
    Message := PrepareToInstall(NeedsRestart);
    SaveStringToFile('{report}', IntToStr(Ord(TestCalled)) + ':' + IntToStr(Ord(Message = '')), False);
    Result := False; Exit;
  end;'''.replace('{report}',quoted(report)))
        # Declare state before NextButtonClick; implementations are placed later.
        source=source.replace('function PrepareToInstall(var NeedsRestart: Boolean): String; forward;',
                              'var TestPresent, TestCalled: Boolean;\nfunction PrepareToInstall(var NeedsRestart: Boolean): String; forward;')
        source=source.replace('var TestPresent, TestCalled: Boolean;\nfunction TestRegKeyExists',
                              'function TestRegKeyExists')
        return source
    executable,report=compile_test_setup(tmp_path,modify)
    run=subprocess.run([str(executable),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/DIR={tmp_path}'],timeout=30)
    expected={'valid':'1:1','default_location':'1:1','bad_marker':'0:0','bad_command':'0:0','uninstall_failed':'1:0'}[scenario]
    assert run.returncode==1 and report.read_text(encoding='utf-8')==expected
    assert (old/'unins000.exe').is_file()
