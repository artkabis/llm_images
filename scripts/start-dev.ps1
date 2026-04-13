<#
.SYNOPSIS
    Démarre le système de reconnaissance faciale en mode local sur Windows.
    Conforme à AGENT_INFRA.md — mode local sans Docker ni Redis.

.DESCRIPTION
    Lance ML (8001), API (8000), Celery worker, Vidéo (8002) et Frontend (3000)
    dans des fenêtres PowerShell séparées.
    Aucun Redis, aucun Docker requis (EventBus in-memory via LOCAL_MODE=true).

.PARAMETER CreateAdmin
    Crée un compte administrateur après le démarrage des services.

.PARAMETER Stop
    Arrête tous les processus uvicorn/celery/node démarrés par ce script.

.EXAMPLE
    .\scripts\start-dev.ps1
    .\scripts\start-dev.ps1 -CreateAdmin
    .\scripts\start-dev.ps1 -Stop
#>
param(
    [switch]$CreateAdmin,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

# ── Helpers ─────────────────────────────────────────────────
function Write-Step { param($msg) Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  !! $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  XX $msg" -ForegroundColor Red; exit 1 }

# ── Arrêt ───────────────────────────────────────────────────
if ($Stop) {
    Write-Step "Arrêt des services..."
    @("uvicorn", "celery") | ForEach-Object {
        Get-Process -Name $_ -ErrorAction SilentlyContinue | Stop-Process -Force
    }
    # Node.js lancé depuis ce projet
    Get-Process -Name "node" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "*frontend*" -or $_.CommandLine -like "*$ROOT*" } |
        Stop-Process -Force
    Write-Ok "Services arrêtés."
    exit 0
}

Write-Host ""
Write-Host "  Facial Recognition System — Mode Local Windows" -ForegroundColor Magenta
Write-Host "  (sans Docker, sans Redis)"
Write-Host ""

# ── Python >= 3.10 ──────────────────────────────────────────
Write-Step "Vérification Python..."
try {
    $pyver = python --version 2>&1
    if ($pyver -match "Python (\d+)\.(\d+)") {
        $maj = [int]$Matches[1]; $min = [int]$Matches[2]
        if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 10)) {
            Write-Fail "Python >= 3.10 requis. Trouvé : $pyver"
        }
        Write-Ok $pyver
    } else {
        Write-Fail "Python non détecté. Installer depuis https://python.org"
    }
} catch {
    Write-Fail "Python introuvable. Installer depuis https://python.org"
}

# ── .env ────────────────────────────────────────────────────
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.local") {
        Copy-Item ".env.local" ".env"
        Write-Ok ".env créé depuis .env.local"
    } elseif (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Warn ".env créé depuis .env.example — penser à éditer les secrets !"
    }
}

# ── Venvs + dépendances ──────────────────────────────────────
$services = @(
    @{ name="ml";    path="services/ml"    },
    @{ name="api";   path="services/api"   },
    @{ name="video"; path="services/video" }
)

foreach ($svc in $services) {
    $venv = Join-Path $ROOT $svc.path ".venv"
    $pip  = Join-Path $venv "Scripts\pip.exe"
    $req  = Join-Path $ROOT $svc.path "requirements.txt"

    if (-not (Test-Path $venv)) {
        Write-Step "Création venv : $($svc.name)"
        python -m venv $venv
    }
    if (Test-Path $req) {
        Write-Step "Dépendances : $($svc.name)"
        & $pip install -q -r $req
        Write-Ok "$($svc.name) prêt"
    }
}

# Frontend npm
$frontPath = Join-Path $ROOT "services/frontend"
if (Test-Path $frontPath) {
    if (-not (Test-Path (Join-Path $frontPath "node_modules"))) {
        Write-Step "npm install : frontend"
        Push-Location $frontPath
        npm install --silent
        Pop-Location
        Write-Ok "frontend prêt"
    }
}

# ── Chemins python par service ───────────────────────────────
$pyML    = Join-Path $ROOT "services/ml/.venv/Scripts/python.exe"
$pyAPI   = Join-Path $ROOT "services/api/.venv/Scripts/python.exe"
$pyVideo = Join-Path $ROOT "services/video/.venv/Scripts/python.exe"

# ── Lancement ────────────────────────────────────────────────
Write-Step "Démarrage service ML (port 8001)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\ml'; `$env:LOCAL_MODE='true'; `$env:INSIGHTFACE_CTX_ID='-1'; & '$pyML' -m uvicorn main:app --host 0.0.0.0 --port 8001"
) -WindowStyle Normal
Start-Sleep -Seconds 3

Write-Step "Démarrage service API (port 8000)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\api'; `$env:LOCAL_MODE='true'; & '$pyAPI' -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

Write-Step "Démarrage Celery worker (memory:// broker)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\api'; `$env:LOCAL_MODE='true'; & '$pyAPI' -m celery -A workers.celery_app worker --pool=solo --loglevel=info"
) -WindowStyle Normal
Start-Sleep -Seconds 2

Write-Step "Démarrage service Vidéo (port 8002)..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$ROOT\services\video'; `$env:LOCAL_MODE='true'; `$env:API_SERVICE_URL='http://localhost:8000'; & '$pyVideo' -m uvicorn main:app --host 0.0.0.0 --port 8002"
) -WindowStyle Normal

if (Test-Path (Join-Path $frontPath "node_modules")) {
    Write-Step "Démarrage frontend React (port 3000)..."
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "cd '$ROOT\services\frontend'; `$env:REACT_APP_API_URL='http://localhost:8000'; npm start"
    ) -WindowStyle Normal
}

# ── Résumé ───────────────────────────────────────────────────
Write-Host ""
Write-Host "  Services démarrés (LOCAL_MODE — sans Docker ni Redis)" -ForegroundColor Green
Write-Host ""
Write-Host "    API REST + Swagger : http://localhost:8000/api/docs" -ForegroundColor White
Write-Host "    Service ML         : http://localhost:8001/health"   -ForegroundColor White
Write-Host "    Service Vidéo      : http://localhost:8002/health"   -ForegroundColor White
Write-Host "    Interface React    : http://localhost:3000"          -ForegroundColor White
Write-Host ""
Write-Host "    Pour arrêter : .\scripts\start-dev.ps1 -Stop"       -ForegroundColor Yellow
Write-Host ""

# ── Création admin optionnelle ───────────────────────────────
if ($CreateAdmin) {
    Write-Step "Attente démarrage API (20s)..."
    Start-Sleep -Seconds 20
    Write-Step "Création compte administrateur..."
    & $pyAPI -c @"
import asyncio, sys
sys.path.insert(0, r'$ROOT\services\api')
from scripts.create_admin import create_admin
asyncio.run(create_admin())
"@
}
