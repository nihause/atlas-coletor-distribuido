; Instalador por usuário: os dados ficam em AppData, fora de {app}.
[Setup]
AppId={{E26FF738-9E3B-4A0F-91C1-978B110BA040}
AppName=ATLAS — Coletor Distribuído
AppVersion={#AppVersion}
AppPublisher=JustiSOFT
AppPublisherURL=https://github.com/nihause/atlas-coletor-distribuido
DefaultDirName={localappdata}\Programs\AtlasColetor
DefaultGroupName=ATLAS Coletor
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=atlas-coletor_{#AppVersion}_windows_amd64
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
AppMutex=Local\JustisoftAtlasColetor
UninstallDisplayIcon={app}\atlas-coletor.exe
VersionInfoVersion={#AppVersion}.0

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ATLAS — Coletor Distribuído"; Filename: "{app}\atlas-coletor.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ATLAS — Coletor Distribuído"; Filename: "{app}\atlas-coletor.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\atlas-coletor.exe"; Description: "Abrir o Atlas"; Flags: nowait postinstall skipifsilent; Check: IsInitialInstall
Filename: "{app}\atlas-coletor.exe"; Parameters: "{code:RestartArguments}"; Flags: nowait; Check: IsAtlasUpdate

[Code]
function OpenProcess(DesiredAccess: LongWord; InheritHandle: Boolean; ProcessId: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function IsAtlasUpdate: Boolean;
begin
  Result := StrToIntDef(ExpandConstant('{param:ATLASWAITPID|0}'), 0) > 0;
end;

function IsInitialInstall: Boolean;
begin
  Result := not IsAtlasUpdate;
end;

function InitializeSetup: Boolean;
var
  Pid: Integer;
  Handle: THandle;
begin
  Result := True;
  Pid := StrToIntDef(ExpandConstant('{param:ATLASWAITPID|0}'), 0);
  if Pid > 0 then begin
    Handle := OpenProcess($00100000, False, Pid);
    if Handle <> 0 then begin
      try
        Result := WaitForSingleObject(Handle, 180000) = 0;
      finally
        CloseHandle(Handle);
      end;
      if not Result then
        MsgBox('O Atlas ainda está aberto. Feche o aplicativo e tente atualizar novamente. Nenhuma tarefa será encerrada à força.', mbError, MB_OK);
    end;
  end;
end;

function RestartArguments(Param: String): String;
var
  EnvPath: String;
begin
  Result := '';
  EnvPath := ExpandConstant('{param:ATLASENV|}');
  if EnvPath <> '' then
    Result := '--env ' + AddQuotes(EnvPath);
  if ExpandConstant('{param:ATLASSTART|0}') = '1' then
    Result := Result + ' --start';
end;
