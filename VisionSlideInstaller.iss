#define MyAppName "VisionSlide"
#define MyAppVersion "1.0.0"
#define MyAppDisplayVersion "v1.0"
#define MyAppPublisher "VisionSlide"
#define MyAppExeName "VisionSlide.exe"
#define MyAppSourceDir "dist\\VisionSlide"
#define MyAppDescription "VisionSlide Presentation Controller"
#define MyAppIcon "assets\\visionslide_app_icon.ico"

[Setup]
AppId={{2CB39E4E-52D1-43E8-BB0C-7609F796A4C3}
AppName={#MyAppName}
AppVerName={#MyAppName} {#MyAppDisplayVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=VisionSlide-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile={#MyAppIcon}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
