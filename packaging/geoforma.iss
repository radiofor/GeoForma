#ifndef AppVersion
  #define AppVersion "1.0.5"
#endif
#ifndef BundleDir
  #define BundleDir "..\release\" + AppVersion + "\portable\GeoForma"
#endif
#ifndef InstallerDir
  #define InstallerDir "..\release\" + AppVersion + "\installer"
#endif

[Setup]
AppId={{E9A728A8-9D4C-49B7-AC67-A6372D7B4E0D}
AppName=GeoForma
AppVersion={#AppVersion}
AppPublisher=GeoForma
DefaultDirName={autopf}\GeoForma
DisableDirPage=no
UsePreviousAppDir=no
AppendDefaultDirName=yes
AllowRootDirectory=yes
DefaultGroupName=GeoForma
PrivilegesRequired=admin
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.22000
OutputDir={#InstallerDir}
OutputBaseFilename=GeoForma-{#AppVersion}-win64-setup
SetupIconFile=..\assets\geoforma_map_pen.ico
UninstallDisplayIcon={app}\GeoForma.exe
AppMutex=Local\GeoForma.Desktop
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Messages]
SetupWindowTitle=安装 %1
UninstallAppTitle=卸载
UninstallAppFullTitle=卸载 %1
ButtonBack=< 上一步
ButtonNext=下一步 >
ButtonInstall=安装
ButtonCancel=取消
ButtonFinish=完成
WelcomeLabel1=欢迎安装 [name]
#ifdef OptionalRuntime
WelcomeLabel2=软件将安装 [name/ver] 和基础组件。首次分割前可自动下载或导入推理运行库及模型权重。
#else
WelcomeLabel2=软件将安装 [name/ver]，自带 Python、地理处理库和默认模型。
#endif
WizardSelectDir=安装位置
SelectDirDesc=选择 [name] 的安装位置
SelectDirLabel3=程序将安装到以下文件夹。
WizardSelectComponents=选择组件
SelectComponentsDesc=选择运行方式
#ifdef OptionalRuntime
SelectComponentsLabel2=基础组件已内封，推理资源在软件“设置 → 资源配置”中按需配置。
#else
SelectComponentsLabel2=软件已携带完整运行依赖。
#endif
WizardReady=准备安装
ReadyLabel1=现在可以开始安装 [name]。如果检测到符合安全校验条件的旧版，将先卸载旧版并保留用户数据，然后继续安装新版。
WizardInstalling=安装中
#ifdef OptionalRuntime
InstallingLabel=正在安装程序和基础组件，请稍候。
#else
InstallingLabel=正在安装程序、依赖和默认模型，请稍候。
#endif
FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=[name] 已安装。
ConfirmUninstall=确认卸载 %1？勾选的数据将被清理，已保存的项目和导出成果会保留。
UninstalledAll=%1 程序已卸载，用户项目已保留。

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "silent-upgrade-marker.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\GeoForma"; Filename: "{app}\GeoForma.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 GeoForma"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GeoForma"; Filename: "{app}\GeoForma.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\GeoForma.exe"; Description: "启动 GeoForma"; Flags: nowait postinstall skipifsilent

[Code]
const
  GeoFormaUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{E9A728A8-9D4C-49B7-AC67-A6372D7B4E0D}_is1';

var
  CleanupMask: Integer;
  UninstallProgress: TOutputMarqueeProgressWizardPage;
  PreviousNextClick: TNotifyEvent;

function InstallDirectory(Directory: String): String;
var
  ParentDirectory: String;
begin
  Directory := Trim(Directory);
  StringChangeEx(Directory, '/', '\', True);
  if (Length(Directory) = 2) and (Directory[2] = ':') then Directory := Directory + '\';
  { Leave invalid or relative paths to Setup's own directory validation. }
  Result := Directory;
  if (Length(Directory) < 3) or (Directory[2] <> ':') or (Directory[3] <> '\') then Exit;
  Directory := RemoveBackslashUnlessRoot(Directory);
  if CompareText(ExtractFileName(Directory), 'GeoForma') = 0 then begin
    ParentDirectory := ExtractFileDir(Directory);
    if CompareText(ExtractFileName(ParentDirectory), 'GeoForma') = 0 then
      Directory := ParentDirectory;
  end else
    Directory := AddBackslash(Directory) + 'GeoForma';
  Result := Directory;
end;

procedure NormalizeDirectoryBeforeNext(Sender: TObject);
begin
  if WizardForm.CurPageID = wpSelectDir then
    WizardForm.DirEdit.Text := InstallDirectory(WizardForm.DirEdit.Text);
  PreviousNextClick(Sender);
end;

procedure InitializeWizard;
var
  I: Integer;
  Argument, Directory: String;
begin
  PreviousNextClick := WizardForm.NextButton.OnClick;
  WizardForm.NextButton.OnClick := @NormalizeDirectoryBeforeNext;
  { Inno resolves /DIR=F: against that drive's current directory before the
    wizard appears. Preserve the user's intended root for that form. }
  for I := 1 to ParamCount do begin
    Argument := ParamStr(I);
    if CompareText(Copy(Argument, 1, 5), '/DIR=') = 0 then begin
      Directory := Copy(Argument, 6, Length(Argument));
      if (Length(Directory) = 2) and (Directory[2] = ':') then
        WizardForm.DirEdit.Text := InstallDirectory(Directory);
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    WizardForm.DirEdit.Text := InstallDirectory(WizardForm.DirEdit.Text);
end;

function InitializeUninstall(): Boolean;
var
  ExitCode: Integer;
begin
  CleanupMask := 0;
  Result := True;
  { Silent uninstall always preserves user data. }
  if UninstallSilent then Exit;
  if not Exec(ExpandConstant('{app}\GeoForma.exe'), '--uninstall-choice', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode) then begin
    MsgBox('无法打开数据清理选项，卸载已取消。', mbError, MB_OK);
    Result := False;
  end else if ExitCode = 1 then
    Result := False
  else if (ExitCode >= 32) and (ExitCode <= 47) then
    CleanupMask := ExitCode - 32
  else begin
    MsgBox('无法读取数据清理选项，卸载已取消。', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExitCode: Integer;
begin
  { Inno's confirmation has been accepted before usUninstall. }
  if (CurUninstallStep = usUninstall) and (CleanupMask <> 0) then begin
    if not Exec(ExpandConstant('{app}\GeoForma.exe'), '--uninstall-cleanup ' + IntToStr(CleanupMask), '', SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode) then
      MsgBox('无法启动数据清理，所选数据已保留。程序将继续卸载。', mbError, MB_OK)
    else if ExitCode <> 0 then
      MsgBox('数据清理未全部完成。程序将继续卸载，请检查资源目录。', mbError, MB_OK);
  end;
end;

function GetFileAttributesW(lpFileName: String): Cardinal;
  external 'GetFileAttributesW@kernel32.dll stdcall';

type
  TShellExecuteInfo = record
    cbSize: DWORD;
    fMask: Cardinal;
    Wnd: HWND;
    lpVerb: String;
    lpFile: String;
    lpParameters: String;
    lpDirectory: String;
    nShow: Integer;
    hInstApp: THandle;
    lpIDList: DWORD;
    lpClass: String;
    hkeyClass: THandle;
    dwHotKey: DWORD;
    hMonitor: THandle;
    hProcess: THandle;
  end;

function ShellExecuteExW(var Info: TShellExecuteInfo): Boolean;
  external 'ShellExecuteExW@shell32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function GetExitCodeProcess(Handle: THandle; var Code: DWORD): Boolean;
  external 'GetExitCodeProcess@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function IsUninstallerName(const Name: String): Boolean;
var I: Integer;
begin
  Result := False;
  if (Length(Name) <> 12) or (CompareText(Copy(Name, 1, 5), 'unins') <> 0) or
     (CompareText(Copy(Name, 9, 4), '.exe') <> 0) then Exit;
  for I := 6 to 8 do
    if (Name[I] < '0') or (Name[I] > '9') then Exit;
  Result := True;
end;

function RunUninstallerWithProgress(const Executable: String; var ExitCode: Integer): Boolean;
var
  Info: TShellExecuteInfo;
  WaitResult, ProcessExitCode: DWORD;
begin
  Result := False;
  Info.cbSize := SizeOf(Info);
  Info.fMask := $00000040; { SEE_MASK_NOCLOSEPROCESS }
  Info.Wnd := 0;
  Info.lpVerb := 'open';
  Info.lpFile := Executable;
  Info.lpParameters := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART';
  Info.lpDirectory := '';
  Info.nShow := SW_HIDE;
  Info.hInstApp := 0;
  Info.lpIDList := 0;
  Info.lpClass := '';
  Info.hkeyClass := 0;
  Info.dwHotKey := 0;
  Info.hMonitor := 0;
  Info.hProcess := 0;
  if not ShellExecuteExW(Info) or (Info.hProcess = 0) then Exit;
  try
    repeat
      WaitResult := WaitForSingleObject(Info.hProcess, 80);
      if WaitResult = $00000102 then UninstallProgress.Animate;
    until WaitResult <> $00000102;
    if (WaitResult <> 0) or not GetExitCodeProcess(Info.hProcess, ProcessExitCode) then Exit;
    ExitCode := ProcessExitCode;
    Result := True;
  finally
    CloseHandle(Info.hProcess);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Count, ExitCode: Integer;
  Location, UninstallCommand, Version, Expected, AttributesPath, Marker: String;
  MarkerText: AnsiString;
  Attributes: Cardinal;
begin
  Result := '';
  Count := 0;
  if RegKeyExists(HKCU, GeoFormaUninstallKey) then Count := Count + 1;
  if RegKeyExists(HKLM32, GeoFormaUninstallKey) then Count := Count + 1;
  if RegKeyExists(HKLM64, GeoFormaUninstallKey) then Count := Count + 1;
  if Count = 0 then Exit;
  if WizardSilent then begin
    Result := '检测到已安装的 GeoForma。静默安装不会自动卸载旧版，请先处理旧版本。';
    Exit;
  end;
  { Identify the machine-wide installation independently of the new target. }
  if (Count <> 1) or not RegKeyExists(HKLM64, GeoFormaUninstallKey) or
     not RegQueryStringValue(HKLM64, GeoFormaUninstallKey, 'InstallLocation', Location) or
     not RegQueryStringValue(HKLM64, GeoFormaUninstallKey, 'UninstallString', UninstallCommand) or
     not RegQueryStringValue(HKLM64, GeoFormaUninstallKey, 'DisplayVersion', Version) then begin
    Result := '检测到多个安装记录或无法确认旧版安装位置。为保护已有数据，请先通过 Windows 已安装的应用处理旧版。';
    Exit;
  end;
  Location := RemoveBackslashUnlessRoot(Location);
  if (Length(Location) < 4) or (Location[2] <> ':') or (Location[3] <> '\') or
     (CompareText(ExpandFileName(Location), Location) <> 0) or
     ((Version <> '1.0.4') and (Version <> '1.0.5')) then begin
    Result := '旧版的位置或版本无法安全验证，请先通过 Windows 已安装的应用卸载旧版，并保留现有数据。';
    Exit;
  end;
  Expected := RemoveQuotes(UninstallCommand);
  if (CompareText(UninstallCommand, '"' + Expected + '"') <> 0) or
     (CompareText(ExtractFileDir(Expected), Location) <> 0) or
     not IsUninstallerName(ExtractFileName(Expected)) then begin
    Result := '旧版卸载程序无法安全验证，请先通过 Windows 已安装的应用卸载旧版。';
    Exit;
  end;
  AttributesPath := Location;
  Attributes := GetFileAttributesW(AttributesPath);
  if (Attributes = $FFFFFFFF) or ((Attributes and $400) <> 0) then begin
    Result := '旧版安装目录无法安全验证，请先通过 Windows 已安装的应用卸载旧版。';
    Exit;
  end;
  Attributes := GetFileAttributesW(Expected);
  if (Attributes = $FFFFFFFF) or ((Attributes and $400) <> 0) then begin
    Result := '旧版卸载程序无法安全验证，请先通过 Windows 已安装的应用卸载旧版。';
    Exit;
  end;
  { Only known releases that explicitly preserve data in silent uninstall may
    be upgraded this way. A version number alone cannot distinguish test builds. }
  Marker := AddBackslash(Location) + 'silent-upgrade-marker.txt';
  Attributes := GetFileAttributesW(Marker);
  if not ((Attributes <> $FFFFFFFF) and ((Attributes and $400) = 0) and
          LoadStringFromFile(Marker, MarkerText) and
          (Trim(MarkerText) = 'GeoForma-' + Version + '-silent-uninstall-preserves-data-v1')) then begin
    Attributes := GetFileAttributesW(AddBackslash(Location) + 'GeoForma.exe');
    if (Version <> '1.0.4') or (Attributes = $FFFFFFFF) or ((Attributes and $400) <> 0) or
       (CompareText(GetSHA256OfFile(AddBackslash(Location) + 'GeoForma.exe'), '829E82A3A67F88B133195FF51701F80E334BF4819CF2D206BE96F85CC6385922') <> 0) or
       (CompareText(GetSHA256OfFile(Expected), '61E8E687CD061A11A9AE822CF8CAB73E8A98EDA21D3405189BE8D58C1CD59DFC') <> 0) then begin
      Result := '无法确认旧版静默卸载会保留数据。请先通过 Windows 已安装的应用卸载旧版，并选择保留数据。';
      Exit;
    end;
  end;
  if CheckForMutexes('Local\GeoForma.Desktop') then begin
    Result := 'GeoForma 正在运行。请先关闭程序并保存工作，然后重试安装。';
    Exit;
  end;
  UninstallProgress := CreateOutputMarqueeProgressPage('正在卸载旧版', '旧版卸载完成后将继续安装新版。');
  UninstallProgress.SetText('正在卸载旧版 GeoForma，请稍候。', '项目和已配置资源将保留。');
  UninstallProgress.Show;
  try
    UninstallProgress.Animate;
    { The original user launches non-default uninstallers rather than passing
      the elevated installer's token to a program in a user-selected folder. }
    if CompareText(Location, ExpandConstant('{autopf}\GeoForma')) = 0 then begin
      if not RunUninstallerWithProgress(Expected, ExitCode) then begin
        Result := '无法启动旧版卸载程序，安装未继续。请检查旧版状态后重试。';
        Exit;
      end;
    end else if not ShellExecAsOriginalUser('open', Expected,
      '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_SHOWNORMAL,
      ewWaitUntilTerminated, ExitCode) then begin
      Result := '无法启动旧版卸载程序，安装未继续。请检查旧版状态后重试。';
      Exit;
    end;
  finally
    UninstallProgress.Hide;
  end;
  if (ExitCode <> 0) or RegKeyExists(HKCU, GeoFormaUninstallKey) or
     RegKeyExists(HKLM32, GeoFormaUninstallKey) or RegKeyExists(HKLM64, GeoFormaUninstallKey) then
    Result := '旧版未完全卸载，安装未继续。请检查旧版状态后重试。';
end;

