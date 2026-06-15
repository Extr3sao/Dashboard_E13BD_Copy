param(
    [switch]$WithFrontend,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'

function Stop-PortProcess {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pidValue = $conn.OwningProcess
        Write-Host "[kill] Port $Port -> PID $pidValue" -ForegroundColor Yellow
        cmd /c "taskkill /PID $pidValue /F" | Out-Null
        Start-Sleep -Seconds 1
    }
}

function Invoke-FrontendBuild {
    Write-Host "[web] running npm build via cmd shim" -ForegroundColor Yellow
    cmd /c "npm.cmd run build"
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed with exit code $LASTEXITCODE"
    }
}

Write-Host "=== run-clean: stop old processes ===" -ForegroundColor Cyan
Stop-PortProcess -Port 8000
Stop-PortProcess -Port 8011
if ($WithFrontend) { Stop-PortProcess -Port 5175 }

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[venv] creating .venv" -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "[pip] install requirements" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

if (-not $NoBuild) {
    Write-Host "[web] build frontend" -ForegroundColor Cyan
    Push-Location src\web-app
    try {
        if (-not (Test-Path node_modules)) {
            npm install
        }
        Invoke-FrontendBuild
    } finally {
        Pop-Location
    }
}

if (-not $env:ORACLE_CLIENT_LIB_DIR) {
    $defaultInstantClient = Join-Path (Get-Location) "instantclient"
    if (Test-Path $defaultInstantClient) {
        $env:ORACLE_CLIENT_LIB_DIR = $defaultInstantClient
        Write-Host "[oracle] ORACLE_CLIENT_LIB_DIR=$defaultInstantClient" -ForegroundColor Cyan
    }
}

Write-Host "[api] starting backend on 127.0.0.1:8011" -ForegroundColor Cyan
$apiProc = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","src.api.main:app","--host","127.0.0.1","--port","8011" `
    -WorkingDirectory "." `
    -RedirectStandardOutput "resources\api-dev.out.log" `
    -RedirectStandardError "resources\api-dev.err.log" `
    -PassThru

if ($WithFrontend) {
    Write-Host "[web] starting vite dev server on 5175" -ForegroundColor Cyan
    $webProc = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c","npm.cmd","run","dev","--","--port","5175" `
        -WorkingDirectory "src\web-app" `
        -RedirectStandardOutput "resources\vite-dev.out.log" `
        -RedirectStandardError "resources\vite-dev.err.log" `
        -PassThru
}

Write-Host "[health] waiting for API" -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $null = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8011/api/profiles"
        $ok = $true
        break
    } catch {
        Start-Sleep -Milliseconds 700
    }
}

if (-not $ok) {
    Write-Host "[error] API did not become healthy. Check resources/api-dev.err.log" -ForegroundColor Red
    exit 1
}

Write-Host "=== run-clean ready ===" -ForegroundColor Green
Write-Host "API PID: $($apiProc.Id)" -ForegroundColor Green
if ($WithFrontend) { Write-Host "WEB PID: $($webProc.Id)" -ForegroundColor Green }
Write-Host "Health endpoint: http://127.0.0.1:8011/api/profiles" -ForegroundColor Green
Write-Host "Deep scan test: http://127.0.0.1:8011/api/audit/deep-scan/ADSL?profile=E13DB" -ForegroundColor Green
Write-Host "Logs: resources/api-dev.out.log, resources/api-dev.err.log" -ForegroundColor Green
if ($WithFrontend) { Write-Host "Logs: resources/vite-dev.out.log, resources/vite-dev.err.log" -ForegroundColor Green }
