; MFViewer Inno Setup Installer Script

[Setup]
AppName=MFViewer
AppVersion=0.3.1
AppPublisher=MFViewer
AppPublisherURL=https://github.com/yourusername/mfviewer
AppSupportURL=https://github.com/yourusername/mfviewer/issues
DefaultDirName={autopf}\MFViewer
DefaultGroupName=MFViewer
OutputDir=dist
OutputBaseFilename=MFViewer-Setup-0.3.1
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
SetupIconFile=Assets\MFViewer.ico
UninstallDisplayIcon={app}\MFViewer.exe
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\MFViewer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MFViewer"; Filename: "{app}\MFViewer.exe"
Name: "{group}\Uninstall MFViewer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MFViewer"; Filename: "{app}\MFViewer.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\MFViewer.exe"; Description: "Launch MFViewer"; Flags: nowait postinstall skipifsilent
