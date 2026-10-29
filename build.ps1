# Compila Isla de Avisos: icono + .exe (carpeta) + portable + instalador.
#
#   .\build.ps1              compila todo
#   .\build.ps1 -SkipSetup   solo los .exe (sin instalador)
#
[CmdletBinding()]
param(
    [switch]$SkipSetup,
    [switch]$SkipPortable,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root

$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Dist = Join-Path $Root "dist"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

# --- 1. Entorno virtual -----------------------------------------------------
if (-not (Test-Path $Python)) {
    Write-Step "Creando entorno virtual"
    python -m venv $Venv
}

Write-Step "Instalando dependencias"
& $Python -m pip install --upgrade pip | Out-Null
& $Python -m pip install -r (Join-Path $Root "requirements.txt")
& $Python -m pip install -r (Join-Path $Root "requirements-dev.txt")

# --- 2. Limpieza ------------------------------------------------------------
if ($Clean) {
    Write-Step "Limpiando builds anteriores"
    Remove-Item -Recurse -Force (Join-Path $Root "build\pyinstaller") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Dist -ErrorAction SilentlyContinue
}

# --- 3. Icono y marcador portable ------------------------------------------
Write-Step "Generando icono"
& $Python (Join-Path $Root "tools\make_icon.py")

New-Item -ItemType Directory -Force -Path (Join-Path $Root "build") | Out-Null
Set-Content -Path (Join-Path $Root "build\portable.marker") -Value "portable" -Encoding ASCII

# --- 4. PyInstaller ---------------------------------------------------------
$WorkPath = Join-Path $Root "build\pyinstaller"

Write-Step "Compilando Isla de Avisos (carpeta)"
& $Python -m PyInstaller --noconfirm --clean `
    --workpath $WorkPath --distpath $Dist `
    (Join-Path $Root "isla_avisos.spec")

if (-not $SkipPortable) {
    Write-Step "Compilando portable (un solo .exe)"
    & $Python -m PyInstaller --noconfirm --clean `
        --workpath $WorkPath --distpath $Dist `
        (Join-Path $Root "isla_avisos_portable.spec")
}

# --- 5. Instalador (Inno Setup) --------------------------------------------
if (-not $SkipSetup) {
    $Iscc = $null
    foreach ($candidate in @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"))) {
        if ($candidate -and (Test-Path $candidate)) { $Iscc = $candidate; break }
    }

    if (-not $Iscc) {
        Write-Step "Instalando Inno Setup con winget"
        winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
        foreach ($candidate in @(
                (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
                (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
                (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"))) {
            if ($candidate -and (Test-Path $candidate)) { $Iscc = $candidate; break }
        }
    }

    if ($Iscc) {
        Write-Step "Compilando instalador"
        & $Iscc (Join-Path $Root "installer\isla_avisos.iss")
    } else {
        Write-Warning "No se encontro ISCC.exe. Instala Inno Setup y vuelve a ejecutar."
    }
}

# --- 6. Resumen -------------------------------------------------------------
Write-Step "Resultado"
Get-ChildItem $Dist | Select-Object Name, Length | Format-Table -AutoSize
Write-Host "Listo." -ForegroundColor Green
exit 0
