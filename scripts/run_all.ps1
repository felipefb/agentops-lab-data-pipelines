# One-command local pipeline: preflight -> tests -> benchmark -> audit -> web build -> E2E.
param([string]$RunId = "", [switch]$NoLLM)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
Set-Location (Split-Path $PSScriptRoot -Parent)
& "$PSScriptRoot\preflight_storage.ps1"; if ($LASTEXITCODE) { throw "BLOCKED: preflight" }
python -m pytest -q; if ($LASTEXITCODE) { throw "tests failed" }
$args_ = @('--seeds', '101', '102', '--baseline-reps', '3')
if ($RunId) { $args_ += @('--run-id', $RunId) }
if ($NoLLM) { $args_ += '--no-llm' }
python -m agentops.benchmark @args_
$latest = (Get-ChildItem "$env:AGENTOPS_ROOT\artifacts\runs" -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
python evaluations\audit_metrics.py $latest; if ($LASTEXITCODE) { throw "audit failed" }
python scripts\scan_secrets.py; if ($LASTEXITCODE) { throw "secret scan failed" }
Push-Location apps\web; npm ci; npx vite build; npx playwright test; Pop-Location
