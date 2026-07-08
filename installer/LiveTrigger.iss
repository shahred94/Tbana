#define MyAppName "LiveTrigger"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.8"
#endif
#ifndef MyDistDir
  #define MyDistDir "dist-v1.0.8"
#endif
#define MyAppPublisher "LiveTrigger"
#define MyAppExeName "LiveTrigger.exe"

[Setup]
AppId={{8F434D30-42AB-4D7B-80D3-2D2E37AA49A0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\LiveTrigger
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=LiveTrigger-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\tibanakstream.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\{#MyDistDir}\LiveTrigger\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\LiveTrigger"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\LiveTrigger"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch LiveTrigger"; Flags: nowait postinstall skipifsilent
