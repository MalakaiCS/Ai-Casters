; Inno Setup script for AI Casters.
; Wraps the PyInstaller one-folder output (dist\AICasters) into a signed-ready
; AICasters-Setup.exe with Start Menu + optional desktop shortcuts.
;
; Build (after PyInstaller):
;   ISCC /DAppVersion=0.1.0 packaging\installer.iss
; Output: dist\installer\AICasters-Setup.exe

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "AI Casters"
#define AppPublisher "AI Casters"
#define AppExeName "AICasters.exe"
#define AppId "{{9F3B7C2A-1E4D-4B6A-9C31-AICASTERS0001}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=AICasters-Setup
SetupIconFile=..\src\ai_caster\ui\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; The entire PyInstaller one-folder build.
Source: "..\dist\AICasters\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
