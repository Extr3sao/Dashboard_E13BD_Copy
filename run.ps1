# run.ps1
$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   SISTEMA D'AUDITORIA ORACLE - PREMIER 4.0    " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

function Test-VenvPython {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        return $false
    }

    try {
        & $VenvPython --version *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function New-ProjectVenv {
    if (Test-Path -LiteralPath $VenvPath) {
        $resolvedVenv = (Resolve-Path -LiteralPath $VenvPath).Path
        if ($resolvedVenv -ne (Join-Path $ProjectRoot ".venv")) {
            throw "Ruta .venv inesperada: $resolvedVenv"
        }

        Write-Host "-> L'entorn virtual .venv existeix pero no funciona. Recreant-lo..." -ForegroundColor Yellow
        Remove-Item -LiteralPath $VenvPath -Recurse -Force
    }
    else {
        Write-Host "-> Creant entorn virtual .venv..." -ForegroundColor Green
    }

    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "No s'ha pogut crear l'entorn virtual .venv"
    }
}

function Invoke-FrontendBuild {
    Write-Host "-> Executant npm run build..." -ForegroundColor Green
    cmd /c "npm.cmd run build"
    if ($LASTEXITCODE -ne 0) {
        throw "El build del frontend ha fallat amb codi $LASTEXITCODE"
    }
}

function Initialize-OracleConnectionTemplate {
    $connectionsPath = Join-Path $ProjectRoot "config\Cadena_conexions.txt"
    $templatePath = Join-Path $ProjectRoot "config\Cadena_conexions.example.txt"

    if ((-not (Test-Path -LiteralPath $connectionsPath)) -and (Test-Path -LiteralPath $templatePath)) {
        Copy-Item -LiteralPath $templatePath -Destination $connectionsPath
        Write-Host "-> Creat config\Cadena_conexions.txt des de la plantilla." -ForegroundColor Yellow
        Write-Host "-> Edita USER, PASSWORD i DSN abans d'executar consultes contra Oracle real." -ForegroundColor Yellow
    }
}

Set-Location $ProjectRoot

Write-Host "`n[1/5] Verificant entorn Python..." -ForegroundColor Yellow
if (-not (Test-VenvPython)) {
    New-ProjectVenv
}

& $VenvPython --version

Write-Host "`n[2/5] Instal.lant dependencies de Python..." -ForegroundColor Yellow
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "La instal.lacio de dependencies Python ha fallat amb codi $LASTEXITCODE"
}

if ($env:BOOTSTRAP_INITIAL_DATA -ne "0") {
    Write-Host "`n[3/5] Carregant dades inicials si cal..." -ForegroundColor Yellow
    & $VenvPython scripts\bootstrap_initial_data.py
    if ($LASTEXITCODE -ne 0) {
        throw "La carrega de dades inicials ha fallat amb codi $LASTEXITCODE"
    }
}
else {
    Write-Host "`n[3/5] Carrega de dades inicials desactivada." -ForegroundColor Yellow
}

Initialize-OracleConnectionTemplate

Write-Host "`n[4/5] Generant build del frontend..." -ForegroundColor Yellow
Set-Location (Join-Path $ProjectRoot "src\web-app")

if (-not (Test-Path -LiteralPath "node_modules")) {
    Write-Host "-> Instal.lant dependencies de Node (npm install)..." -ForegroundColor Green
    cmd /c "npm.cmd install"
    if ($LASTEXITCODE -ne 0) {
        throw "La instal.lacio de dependencies Node ha fallat amb codi $LASTEXITCODE"
    }
}

Invoke-FrontendBuild
Set-Location $ProjectRoot

Write-Host "`n[5/5] Iniciant sistema unificat (http://127.0.0.1:8000)..." -ForegroundColor Yellow
Write-Host "-> Prem CTRL+C per aturar el servidor." -ForegroundColor Green
& $VenvPython -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) {
    throw "El servidor ha finalitzat amb codi $LASTEXITCODE"
}
