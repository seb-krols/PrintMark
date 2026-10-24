; Per-user install: no administrator rights; config and audit history live in AppData.
#ifndef AppVersion
  #error AppVersion must be supplied by build_windows.ps1
#endif

[Setup]
AppId={{7DA5BD62-00DD-4859-8BDF-C64A0A4FBC70}
AppName=BaseMark
AppVersion={#AppVersion}
AppPublisher=Sebastians Krols
AppPublisherURL=https://github.com/seb-krols/PrintMark
DefaultDirName={localappdata}\Programs\BaseMark
DefaultGroupName=BaseMark
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=basemark-{#AppVersion}-windows-x64-setup
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\basemark-desktop.exe
CloseApplications=yes

[InstallDelete]
; Replace the shared runtime on upgrade so no stale DLLs from an older build remain.
Type: filesandordirs; Name: "{app}\_internal"
; Start menu shortcut name used before 0.4.0.
Type: files; Name: "{group}\BaseMark Settings.lnk"

[Files]
Source: "..\build\windows-payload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BaseMark"; Filename: "{app}\basemark-desktop.exe"
Name: "{group}\BaseMark Installation Guide"; Filename: "{app}\INSTALL.md"

[Run]
Filename: "{app}\basemark-desktop.exe"; Description: "Open BaseMark"; Flags: nowait postinstall skipifsilent

; Deliberately no UninstallDelete for AppData: preserve IDs, settings and logs.
