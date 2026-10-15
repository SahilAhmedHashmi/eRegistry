#define MyAppName "eRegistry"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "eRegistry"
#define MyAppExeName "eRegistry.exe"

[Setup]
AppId={{7E926D1A-20B4-48E3-8C30-E1F427FA6635}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\eRegistry
DefaultGroupName=eRegistry
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=eRegistry-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\eRegistry\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\eRegistry"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\eRegistry"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch eRegistry"; Flags: nowait postinstall skipifsilent

