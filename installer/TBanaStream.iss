#define MyAppName "TBana Stream"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.1"
#endif
#ifndef MyDistDir
  #define MyDistDir "dist-v1.1.1"
#endif
#define MyAppPublisher "TBana Stream"
#define MyAppExeName "TBana Stream.exe"

[Setup]
AppId={{8F434D30-42AB-4D7B-80D3-2D2E37AA49A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TBana Stream
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=..\release
OutputBaseFilename=TBana-Stream-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\tibanakstream.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\{#MyDistDir}\TBana Stream\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\TBana Stream"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\TBana Stream"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch TBana Stream"; Flags: nowait postinstall skipifsilent runascurrentuser
