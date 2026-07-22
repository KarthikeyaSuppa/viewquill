# Run the Quillnight sidecar + frontend together for local dev.
# Usage:  ./scripts/dev.ps1     (from repo root)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sidecar = Join-Path $root 'apps/sidecar'
$desktop = Join-Path $root 'apps/desktop'

# Dev app-data (SQLite/media/audio) in a gitignored folder under the sidecar.
$env:QUILLNIGHT_DATA_DIR = Join-Path $sidecar 'app-data'
$py = Join-Path $sidecar '.venv/Scripts/python.exe'

if (-not (Test-Path $py)) {
  Write-Error "Sidecar venv missing. Run: cd apps/sidecar; python -m venv .venv; ./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt"
}

Write-Host "Starting sidecar on http://127.0.0.1:8756 ..." -ForegroundColor Cyan
$sidecarJob = Start-Job -ScriptBlock {
  param($py, $sidecar, $dataDir)
  Set-Location $sidecar
  $env:QUILLNIGHT_DATA_DIR = $dataDir
  # This build laptop has no LLM/STT models (docs/CLAUDE.md). Run the AI paths in
  # stub mode so Enhance/dictation are exercisable offline; unset on the AI laptop.
  $env:QUILLNIGHT_LLM_STUB = '1'
  $env:QUILLNIGHT_STT_STUB = '1'
  & $py -m app.main
} -ArgumentList $py, $sidecar, $env:QUILLNIGHT_DATA_DIR

try {
  Write-Host "Starting frontend on http://localhost:1420 ..." -ForegroundColor Cyan
  Set-Location $desktop
  npm run dev
}
finally {
  Write-Host "Stopping sidecar..." -ForegroundColor Yellow
  Stop-Job $sidecarJob -ErrorAction SilentlyContinue
  Remove-Job $sidecarJob -ErrorAction SilentlyContinue
}
