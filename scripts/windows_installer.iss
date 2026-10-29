; Per-user install: no administrator rights; config and audit history live in AppData.
; One page: "Connect PrusaSlicer now", then Install.
; Silent install: setup.exe /VERYSILENT  (add /CONNECT=no to leave PrusaSlicer untouched)
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
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=basemark-{#AppVersion}-windows-x64-setup
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
; Background check at login: warns about exports from presets without BaseMark.
Name: "{userstartup}\BaseMark export check"; Filename: "{app}\basemark-desktop.exe"; Parameters: "--watch"

[Run]
Filename: "{app}\basemark-desktop.exe"; Parameters: "--watch"; Flags: nowait
Filename: "{app}\basemark-desktop.exe"; Description: "Open BaseMark"; Flags: nowait postinstall skipifsilent

; Deliberately no UninstallDelete for AppData: preserve IDs, settings and logs.

[Code]
var
  SetupPage: TWizardPage;
  ConnectBox: TNewCheckBox;

function App(): String;
begin
  Result := ExpandConstant('{app}\basemark.exe');
end;

procedure InitializeWizard;
var
  Hint: TNewStaticText;
begin
  SetupPage := CreateCustomPage(wpWelcome, 'Connect PrusaSlicer',
    'BaseMark stamps the material into the bottom of every exported part.');

  ConnectBox := TNewCheckBox.Create(SetupPage);
  ConnectBox.Parent := SetupPage.Surface;
  ConnectBox.Width := SetupPage.SurfaceWidth;
  ConnectBox.Height := ScaleY(22);
  ConnectBox.Caption := 'Connect PrusaSlicer now (recommended)';
  ConnectBox.Checked := CompareText(ExpandConstant('{param:CONNECT|yes}'), 'no') <> 0;

  Hint := TNewStaticText.Create(SetupPage);
  Hint.Parent := SetupPage.Surface;
  Hint.Top := ConnectBox.Top + ConnectBox.Height + ScaleY(4);
  Hint.Left := ScaleX(18);
  Hint.Width := SetupPage.SurfaceWidth - ScaleX(18);
  Hint.WordWrap := True;
  { No line may start with "#": the preprocessor would read it as a directive. }
  Hint.Caption := 'Adds "+ BaseMark" copies of the print and printer presets selected in ' +
    'PrusaSlicer (stamp on export, arc fitting off, plain G-code) and selects them. ' +
    'Your own presets are not changed. PrusaSlicer needs to be closed for this step.' + #13#10#13#10 +
    'Labels show the material, e.g. PLA. A part number can be switched on later in BaseMark.';
end;

{ The running export check holds the program files open: end it before replacing them. }
procedure StopWatcher();
var
  Code: Integer;
begin
  if FileExists(App()) then
    Exec(App(), '--stop-watcher', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopWatcher();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopWatcher();
  Result := True;
end;

{ The Ready page is disabled, so this page starts the install. }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = SetupPage.ID then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);
end;

procedure ConnectPrusaSlicer();
var
  Code: Integer;
begin
  { Already connected (e.g. an upgrade): leave PrusaSlicer's settings alone. }
  if Exec(App(), '--check-prusaslicer', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0) then
    Exit;
  repeat
    if not Exec(App(), '--setup-prusaslicer', '', SW_HIDE, ewWaitUntilTerminated, Code) then
      Code := 1;
    { Exit code 3: PrusaSlicer is open and would overwrite the change when it closes. }
    if (Code = 3) and not WizardSilent() then
    begin
      if MsgBox('PrusaSlicer is open. Close it, then click Retry to connect it.' + #13#10#13#10 +
                'Cancel skips this step. BaseMark''s Overview can do it later ' +
                '(Set up PrusaSlicer).', mbInformation, MB_RETRYCANCEL) <> IDRETRY then
        Exit;
    end
    else
      Break;
  until False;
  if (Code <> 0) and not WizardSilent() then
    MsgBox('PrusaSlicer could not be connected automatically (has it been opened once on ' +
           'this PC?). BaseMark''s Overview shows what is missing.', mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and ConnectBox.Checked then
    ConnectPrusaSlicer();
end;
