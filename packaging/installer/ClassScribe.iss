; ClassScribe Windows Inno Setup Script
; Packages the pre-built standalone directory dist\ClassScribe

#define MyAppName "ClassScribe"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "ClassScribe"
#define MyAppURL "https://github.com/luismariofg132/Meet-transcript"
#define MyAppExeName "ClassScribe.exe"
#define MyAppIcon "..\assets\classscribe.ico"
#define MySourceDir "..\..\dist\ClassScribe"

[Setup]
AppId={{8B1F54B0-7C5C-4E1B-9A82-3A6D7C5CFC01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=ClassScribe-Setup-{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyAppIcon}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\classscribe.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\classscribe.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up application directory only.
; User data (Documents\ClassScribe and AppConfigLocation) is stored outside {app}
; and is intentionally preserved across installs/uninstalls.
Type: files; Name: "{app}\*.log"
