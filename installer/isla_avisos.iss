; Instalador de Isla de Avisos (Inno Setup 6)
; Instalacion por usuario (sin administrador) en %LOCALAPPDATA%\Programs.

#define AppName "Isla de Avisos"
#define AppVersion "0.1.0"
#define AppPublisher "Isla de Avisos"
#define AppExeName "Isla de Avisos.exe"
#define RunValueName "IslaAvisos"

[Setup]
AppId={{8F3C2A64-5B1D-4E77-9C2A-0D5B7E1F4A93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=IslaAvisos-Setup-{#AppVersion}
SetupIconFile=..\assets\isla_avisos.ico
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce
Name: "startup"; Description: "Iniciar Isla de Avisos al encender Windows"; GroupDescription: "Arranque automatico:"; Flags: unchecked

[Files]
Source: "..\dist\Isla de Avisos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#RunValueName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
{ Cierra la app si esta abierta antes de instalar o desinstalar. }
procedure CloseRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/IM "{#AppExeName}" /F', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  CloseRunningApp();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  CloseRunningApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\IslaAvisos');
    if DirExists(DataDir) then
    begin
      if MsgBox('¿Quieres borrar tambien la configuracion y el registro de {#AppName}?'
                + #13#10 + #13#10 + DataDir,
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
