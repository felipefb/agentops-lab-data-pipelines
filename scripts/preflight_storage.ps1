# Phase 0 storage preflight. Fails closed (exit 1) when any controllable write path is outside the workspace volume.
param([string]$RunId = "")
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
$root = $env:AGENTOPS_ROOT
$drive = (Split-Path -Qualifier $root)
$checks = @()
function Add-Check($name, $ok, $detail) { $script:checks += [ordered]@{ name = $name; status = $(if ($ok) { 'PASS' } else { 'FAIL' }); detail = "$detail" } }

# 1. Volume exists, free space, write permission
$vol = Get-PSDrive -Name $drive.TrimEnd(':') -ErrorAction SilentlyContinue
Add-Check 'volume_exists' ($null -ne $vol) $drive
if ($null -eq $vol) { Write-Error "Volume $drive not found. BLOCKED: define another volume explicitly; C: is NOT a fallback." }
$freeGB = [math]::Round($vol.Free / 1GB, 1)
Add-Check 'free_space_ge_20GB' ($freeGB -ge 20) "$freeGB GB free"
$probe = Join-Path $root "tmp\write_probe_$PID.txt"
try { 'probe' | Out-File -Encoding utf8 $probe; Remove-Item $probe; Add-Check 'write_permission' $true $root } catch { Add-Check 'write_permission' $false $_ }
Add-Check 'workspace_not_on_C' (-not $root.ToUpper().StartsWith('C:')) $root

# 2. Every controllable env var resolves under the workspace
$vars = 'TEMP','TMP','TMPDIR','PIP_CACHE_DIR','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','TORCH_HOME','XDG_CACHE_HOME','NPM_CONFIG_CACHE','PLAYWRIGHT_BROWSERS_PATH','PYTHONPYCACHEPREFIX','RUFF_CACHE_DIR','AGENTOPS_DATA_DIR','AGENTOPS_ARTIFACTS_DIR','AGENTOPS_LOG_DIR','DUCKDB_TMP_DIR','VIRTUAL_ENV'
foreach ($v in $vars) {
  $val = [Environment]::GetEnvironmentVariable($v)
  $ok = $val -and ([IO.Path]::GetFullPath($val)).ToUpper().StartsWith($root.ToUpper())
  Add-Check "env:$v" $ok $val
}

# 3. Real paths of repo / venv / node_modules (resolve junctions & symlinks)
foreach ($p in @("$root\repo", "$root\venv", "$root\repo\apps\web\node_modules")) {
  if (Test-Path $p) {
    $item = Get-Item $p -Force
    $target = if ($item.LinkType) { $item.Target } else { $item.FullName }
    Add-Check "realpath:$p" ("$target".ToUpper().StartsWith($drive.ToUpper())) $target
  }
}
# npm global config cache, Python's tempfile, uv cache as seen by the tools
$npmCache = (& npm config get cache 2>$null)
Add-Check 'npm_effective_cache' ("$npmCache".ToUpper().StartsWith($root.ToUpper())) $npmCache
$py = if (Test-Path "$root\venv\Scripts\python.exe") { "$root\venv\Scripts\python.exe" } else { 'python' }
$pyTmp = (& $py -c "import tempfile;print(tempfile.gettempdir())")
Add-Check 'python_tempfile_dir' ("$pyTmp".ToUpper().StartsWith($root.ToUpper())) $pyTmp

# 4. Docker / WSL (informational; not installed => not a write source)
$docker = Get-Command docker -ErrorAction SilentlyContinue
Add-Check 'docker_storage' $true $(if ($docker) { 'docker present: verify data-root manually' } else { 'docker not installed (Airflow/Postgres containers BLOCKED)' })

# 5. Known uncontrollable writes (documented, not claimed zero)
$notes = @(
  'Windows OS, Defender, Prefetch, pagefile and browser profile internals may write to C: outside project control.',
  'Python interpreter itself is installed on C: (read-only use); no project writes target it.',
  'This audit verifies configured paths; it does NOT prove zero writes to C:.'
)

$failed = @($checks | Where-Object { $_.status -eq 'FAIL' })
$result = [ordered]@{
  timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
  workspace = $root; volume = $drive; free_gb = $freeGB
  status = $(if ($failed.Count -eq 0) { 'PASS' } else { 'FAIL' })
  checks = $checks; uncontrollable_notes = $notes
}
$outDir = if ($RunId) { "$root\artifacts\runs\$RunId" } else { "$root\artifacts\preflight" }
New-Item -ItemType Directory -Force $outDir | Out-Null
$result | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 "$outDir\storage_audit.json"
$checks | ForEach-Object { '{0,-5} {1} -> {2}' -f $_.status, $_.name, $_.detail }
"PREFLIGHT: $($result.status)  ($outDir\storage_audit.json)"
if ($failed.Count -gt 0) { exit 1 }
