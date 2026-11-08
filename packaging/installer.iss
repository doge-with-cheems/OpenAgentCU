#define MyAppName "OpenAgentCU"
#define MyAppVersion "2.0.0"
#define MyAppExeName "OpenAgentCU.exe"
#define MyAppId "{{8F3A2C1E-6B4D-4E7A-9C2F-1D5A7B3E9C42}"
#ifndef MyPrivileges
  #define MyPrivileges "admin"
#endif
#ifndef MyOutputSuffix
  #define MyOutputSuffix ""
#endif
#ifndef MyUninstallable
  #define MyUninstallable "yes"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=OpenAgentCU
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired={#MyPrivileges}
PrivilegesRequiredOverridesAllowed=commandline dialog
OutputDir=..\dist\installer
OutputBaseFilename=OpenAgentCU-{#MyAppVersion}-Setup{#MyOutputSuffix}
SetupIconFile=OpenAgentCU.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Uninstallable={#MyUninstallable}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}.0
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCompany=OpenAgentCU
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}

[Languages]
Name: "zhcn"; MessagesFile: "ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "..\dist\OpenAgentCU\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\oacu 命令行"; Filename: "{cmd}"; Parameters: "/k ""{app}\oacu.exe"" --help"; WorkingDir: "{app}"; IconFilename: "{app}\oacu.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  { 某些精简/新建用户的 Roaming、开始菜单目录可能缺失，先补齐再创建快捷方式 }
  if CurStep = ssInstall then
  begin
    ForceDirectories(ExpandConstant('{userappdata}'));
    ForceDirectories(ExpandConstant('{localappdata}'));
    ForceDirectories(ExpandConstant('{autoprograms}'));
    ForceDirectories(ExpandConstant('{userdesktop}'));
  end;
end;
