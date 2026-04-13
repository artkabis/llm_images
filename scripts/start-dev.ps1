<#
.SYNOPSIS
    Démarre le système de reconnaissance faciale en LOCAL_MODE sur Windows.
    Équivalent PowerShell de scripts/start-dev.sh.
    Conforme AGENT_INFRA.md — mode local sans Docker, sans Redis.

.DESCRIPTION
    Lance ML (:8001), API (:8000), Celery, Vidéo (:8002) et Frontend (:3000)
    dans des fenêtres PowerShell séparées. Aucun Docker requis.

.PARAMETER CreateAdmin
    Crée un compte administrateur après le démarrage (attend 15s).

.PARAMETER Stop
    Arrête tous les processus démarrés.

.EXAMPLE
    .\scripts\start-dev.ps1
    .\scripts\start-dev.ps1 -CreateAdmin
    .\scripts\start-dev.ps1 -Stop
#>
param([switch]$CreateAdmin, [switch]$Stop)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

function Write-Step { param($m) Write-Host "[>] $m" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "[!] $m" -ForegroundColor Yellow }
function Write-Fail { param($m) Write-Host "[X] $m" -ForegroundColor Red }

# ── Arrêt ────────────────────────────────────────────────────────────────
if ($Stop) {
    Write-Step "Arrêt des services..."
    @("uvicorn", "celery") | ForEach-Object {
        Get-Process -Name $_ -ErrorAction SilentlyContinue | Stop-Process -Force
    }
    Get-Process -Name "node" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*frontend*" } |
        Stop-Process -Force
    Write-Ok "Services arrêtés."
    exit 0
}

# ── Python ────────────────────────────────────────────────────────────
try {
    $v = python --version 2>&1
    if ($v -match "Python (\d+)\.(\d+)") {
        if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 10)) {
            Write-Fail "Python >= 3.10 requis. Trouvé : $v"; exit 1
        }
        Write-Ok $v
    }
} catch { Write-Fail "Python introuvable. Installer depuis https://python.org"; exit 1 }

# ── .env ────────────────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    $src = if (Test-Path ".env.local") { ".env.local" }
           elseif (Test-Path ".env.example") { ".env.example" }
           else { $null }
    if ($src) { Copy-Item $src ".env"; Write-Ok ".env créé depuis $src" }
}

# ── Venvs ───────────────────────────────────────────────────────────────
@("services/ml", "services/api", "services/video") | ForEach-Object {
    $svc = $_
    $venv = "$svc/.venv"
    if (-not (Test-Path $venv)) {
        Write-Step "Création venv : $svc"
        python -m venv $venv
    }
    $pip = "$venv/Scripts/pip.exe"
    $req = "$svc/requirements.txt"
    if (Test-Path $req) {
        Write-Step "Installation dépendances : $svc"
        & $pip install -q -r $req
        Write-Ok "$svc prêt"
    }
}

# Frontend npm
if ((Test-Path "services/frontend") -and -not (Test-Path "services/frontend/node_modules")) {
    Write-Step "npm install frontend..."
    Push-Location "services/frontend"; npm install --silent; Pop-Location
    Write-Ok "frontend npm prêt"
}

# ── Lancement ────────────────────────────────────────────────────────────
Write-Step "Démarrage des services (LOCAL_MODE=true)..."

$pyML  = "$ROOT\services\ml\.venv\Scripts\python.exe"
$pyAPI = "$ROOT\services\api\.venv\Scripts\python.exe"
$pyVid = "$ROOT\services\video\.venv\Scripts\python.exe"

# ML Service
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\ml'; `$env:LOCAL_MODE='true'; `$env:INSIGHTFACE_CTX_ID='-1'; & '$pyML' -m uvicorn main:app --host 0.0.0.0 --port 8001"
) -WindowStyle Normal
Start-Sleep -Seconds 3

# API
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\api'; `$env:LOCAL_MODE='true'; & '$pyAPI' -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

# Celery (mode solo — memory:// broker)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\api'; `$env:LOCAL_MODE='true'; & '$pyAPI' -m celery -A workers.celery_app worker --pool=solo --loglevel=info"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# Vidéo
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\video'; `$env:LOCAL_MODE='true'; `$env:API_SERVICE_URL='http://localhost:8000'; & '$pyVid' -m uvicorn main:app --host 0.0.0.0 --port 8002"
) -WindowStyle Normal

# Frontend
if (Test-Path "services/frontend/node_modules") {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$ROOT\services\frontend'; `$env:REACT_APP_API_URL='http://localhost:8000'; npm start"
    ) -WindowStyle Normal
}

# ── Résumé ────────────────────────────────────────────────────────────
Write-Host ""
Write-Ok "Services démarrés — LOCAL_MODE (sans Docker / Redis)"
Write-Host ""
Write-Host "  API REST      : http://localhost:8000/api/docs" -ForegroundColor White
Write-Host "  Service ML    : http://localhost:8001/health"   -ForegroundColor White
Write-Host "  Service Vidéo : http://localhost:8002/health"   -ForegroundColor White
Write-Host "  Interface UI  : http://localhost:3000"          -ForegroundColor White
Write-Host ""
Write-Host "  Arrêter : .\scripts\start-dev.ps1 -Stop" -ForegroundColor Yellow
Write-Host ""

if ($CreateAdmin) {
    Write-Step "Attente démarrage API (15s)..."
    Start-Sleep -Seconds 15
    Write-Step "Création du compte administrateur..."
    & $pyAPI -c @"
import asyncio, sys
sys.path.insert(0, r'$ROOT\services\api')
from scripts.create_admin import create_admin
asyncio.run(create_admin())
"@
}
