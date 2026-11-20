; Instalador de Miky (Inno Setup 6)
; Compilar con: ISCC.exe installer\miky.iss
; Requiere que dist\Miky\ esté construido (tools\build_exe.py).

#define AppName "Miky"
#define AppVersion "0.1.0b3"
#define AppPublisher "Daniel Orlando Lugo"
#define AppURL "https://github.com/ildany86/Micky-Assistant"
#define AppExeName "Miky.exe"

[Setup]
AppId={{7C4A1B2E-9F3D-4A6B-8E21-5C0D9B7A3F18}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instalación por usuario: no pide administrador.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=Miky-{#AppVersion}-setup
SetupIconFile=..\src\miky\data\assets\logo.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\Miky\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Diagnóstico de {#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "diagnostics"; Flags: runminimized
Name: "{group}\Cómo probar {#AppName}"; Filename: "{#AppURL}\blob\main\docs\10-probar.md"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Todo lo que genera PyInstaller y no está en la lista de archivos.
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
