# Recurring dependency audit across all three ecosystems (docs/02 §security).
# Run periodically and in CI. Non-fatal: reports issues, doesn't block.
$root = Split-Path $PSScriptRoot -Parent

Write-Host "== npm audit (frontend) ==" -ForegroundColor Cyan
Push-Location (Join-Path $root 'apps/desktop')
try { npm audit } catch { Write-Warning "npm audit reported issues" }
Pop-Location

Write-Host "== pip-audit (sidecar) ==" -ForegroundColor Cyan
$py = Join-Path $root 'apps/sidecar/.venv/Scripts/python.exe'
if (Test-Path $py) {
  & $py -m pip install --quiet pip-audit 2>$null
  try { & $py -m pip_audit -r (Join-Path $root 'apps/sidecar/requirements.lock.txt') }
  catch { Write-Warning "pip-audit reported issues" }
} else {
  Write-Warning "Sidecar venv not found; skipping pip-audit."
}

Write-Host "== cargo audit (Tauri shell) ==" -ForegroundColor Cyan
if (Get-Command cargo -ErrorAction SilentlyContinue) {
  Push-Location (Join-Path $root 'apps/desktop/src-tauri')
  try { cargo audit } catch { Write-Warning "cargo audit reported issues or src-tauri not present yet" }
  Pop-Location
} else {
  Write-Warning "cargo not installed; skipping cargo audit (Tauri shell deferred)."
}
