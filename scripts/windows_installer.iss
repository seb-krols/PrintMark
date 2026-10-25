; Per-user install: no administrator rights; config and audit history live in AppData.
; One page: this PC's ID prefix and "Connect PrusaSlicer now", then Install.
; Silent shop deployment: setup.exe /VERYSILENT /PREFIX=B  (add /CONNECT=no to skip PrusaSlicer)
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

[Run]
Filename: "{app}\basemark-desktop.exe"; Description: "Open BaseMark"; Flags: nowait postinstall skipifsilent

; Deliberately no UninstallDelete for AppData: preserve IDs, settings and logs.

[Code]
var
  SetupPage: TWizardPage;
  PrefixEdit: TNewEdit;
  ConnectBox: TNewCheckBox;

function App(): String;
begin
  Result := ExpandConstant('{app}\basemark.exe');
end;

{ The prefix already saved on this PC (upgrades), read from config.toml. }
function ExistingPrefix(): String;
var
  Lines: TArrayOfString;
  I, First, Last: Integer;
  Line: String;
begin
  Result := '';
  if not LoadStringsFromFile(ExpandConstant('{userappdata}\BaseMark\config.toml'), Lines) then
    Exit;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    Line := Trim(Lines[I]);
    if (Pos('counter_prefix', Line) > 0) and (Pos('#', Line) <> 1) then
    begin
      First := Pos('"', Line);
      Line := Copy(Line, First + 1, Length(Line));
      Last := Pos('"', Line);
      if (First > 0) and (Last > 0) then
        Result := Copy(Line, 1, Last - 1);
    end;
  end;
end;

{ Same rule as BaseMark: up to 12 letters, digits, "_" or "-". }
function ValidPrefix(Value: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := Length(Value) <= 12;
  for I := 1 to Length(Value) do
  begin
    C := Value[I];
    if not (((C >= 'A') and (C <= 'Z')) or ((C >= 'a') and (C <= 'z')) or
            ((C >= '0') and (C <= '9')) or (C = '_') or (C = '-')) then
      Result := False;
  end;
end;

procedure InitializeWizard;
var
  Intro, Example, Hint: TNewStaticText;
begin
  SetupPage := CreateCustomPage(wpWelcome, 'Set up this computer',
    'Both can be changed later in BaseMark.');

  Intro := TNewStaticText.Create(SetupPage);
  Intro.Parent := SetupPage.Surface;
  Intro.WordWrap := True;
  Intro.Width := SetupPage.SurfaceWidth;
  Intro.Caption := 'Computer prefix. Part IDs start with it, so give every PC in the shop ' +
    'its own letter:';

  PrefixEdit := TNewEdit.Create(SetupPage);
  PrefixEdit.Parent := SetupPage.Surface;
  PrefixEdit.Top := Intro.Top + Intro.Height + ScaleY(8);
  PrefixEdit.Width := ScaleX(90);
  PrefixEdit.MaxLength := 12;
  PrefixEdit.Text := ExpandConstant('{param:PREFIX|}');
  if PrefixEdit.Text = '' then
    PrefixEdit.Text := ExistingPrefix();

  Example := TNewStaticText.Create(SetupPage);
  Example.Parent := SetupPage.Surface;
  Example.Top := PrefixEdit.Top + ScaleY(3);
  Example.Left := PrefixEdit.Left + PrefixEdit.Width + ScaleX(10);
  Example.Caption := 'e.g. A  ->  labels like >PLA< A042';

  ConnectBox := TNewCheckBox.Create(SetupPage);
  ConnectBox.Parent := SetupPage.Surface;
  ConnectBox.Top := PrefixEdit.Top + PrefixEdit.Height + ScaleY(26);
  ConnectBox.Width := SetupPage.SurfaceWidth;
  ConnectBox.Caption := 'Connect PrusaSlicer now (recommended)';
  ConnectBox.Checked := CompareText(ExpandConstant('{param:CONNECT|yes}'), 'no') <> 0;

  Hint := TNewStaticText.Create(SetupPage);
  Hint.Parent := SetupPage.Surface;
  Hint.Top := ConnectBox.Top + ConnectBox.Height + ScaleY(4);
  Hint.Left := ScaleX(18);
  Hint.Width := SetupPage.SurfaceWidth - ScaleX(18);
  Hint.WordWrap := True;
  Hint.Caption := 'Adds "+ BaseMark" copies of the print and printer presets selected in ' +
    'PrusaSlicer (stamp on export, arc fitting off, plain G-code) and selects them. ' +
    'Your own presets are not changed. PrusaSlicer needs to be closed for this step.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = SetupPage.ID) and not ValidPrefix(Trim(PrefixEdit.Text)) then
  begin
    MsgBox('Use up to 12 letters, numbers, "_" or "-" for the prefix.', mbError, MB_OK);
    Result := False;
  end;
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
var
  Code: Integer;
  Prefix: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Prefix := Trim(PrefixEdit.Text);
  if (Prefix <> ExistingPrefix()) and ValidPrefix(Prefix) then
    Exec(App(), '--set-prefix "' + Prefix + '"', '', SW_HIDE, ewWaitUntilTerminated, Code);
  if ConnectBox.Checked then
    ConnectPrusaSlicer();
end;
