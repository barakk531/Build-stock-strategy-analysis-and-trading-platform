#Requires -Version 5
<#
  One-command dev launcher for the Stock Strategy Platform.

  Brings up the Postgres database (Docker) and then runs the three app
  processes host-natively — backend (FastAPI), frontend (Vite), and the
  Market Analyst (Streamlit) — each in its own window. Any service already
  listening on its port is left alone, so re-running this is safe.

  Usage:  powershell -ExecutionPolicy Bypass -File dev.ps1   (or run dev.cmd)
#>

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot

function Test-Port([int]$port) {
  try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $port); $c.Close(); $true }
  catch { $false }
}

function Start-Svc([string]$title, [string]$cmd) {
  Start-Process powershell -ArgumentList '-NoExit', '-NoProfile', '-Command',
    "`$Host.UI.RawUI.WindowTitle = '$title'; $cmd"
}

Write-Host 'Stock Strategy Platform - dev launcher' -ForegroundColor Cyan

# 1) Docker engine + Postgres. The app containers are NOT built here (host-native
#    pip/npm is the supported path on this machine); only the DB runs in Docker.
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'Docker engine not running - starting Docker Desktop...' -ForegroundColor Yellow
  $dd = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
  if (Test-Path $dd) { Start-Process $dd }
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 3
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { break }
  }
}
if ($LASTEXITCODE -eq 0) {
  Write-Host 'Starting Postgres (docker compose up -d db)...' -ForegroundColor Yellow
  docker compose -f (Join-Path $root 'docker-compose.yml') up -d db | Out-Null
} else {
  Write-Host 'WARNING: Docker unavailable - database pages will not work.' -ForegroundColor Red
}

# 2) App services (skip any that are already listening).
if (Test-Port 8000) { Write-Host 'backend  already on :8000 - skipping' -ForegroundColor DarkGray }
else { Start-Svc 'backend' "Set-Location '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" }

if (Test-Port 5173) { Write-Host 'frontend already on :5173 - skipping' -ForegroundColor DarkGray }
else { Start-Svc 'frontend' "Set-Location '$root\frontend'; npm run dev" }

if (Test-Port 8501) { Write-Host 'analyst  already on :8501 - skipping' -ForegroundColor DarkGray }
else { Start-Svc 'analyst' "Set-Location '$root\analyst'; .\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false" }

Write-Host ''
Write-Host 'Launched:' -ForegroundColor Green
Write-Host '  Website         http://localhost:5173/'
Write-Host '  Backend API     http://localhost:8000/docs'
Write-Host '  Market Analyst  http://localhost:8501/'
Write-Host 'Each service runs in its own window; close a window to stop that service.'
