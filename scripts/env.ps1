# Dot-source this file:  . .\scripts\env.ps1
# Points every controllable cache/temp/persistence path at the AgentOps workspace (default E:\AgentOpsLab).
$ErrorActionPreference = 'Stop'
if (-not $env:AGENTOPS_ROOT) { $env:AGENTOPS_ROOT = 'E:\AgentOpsLab' }
$root = $env:AGENTOPS_ROOT
$map = [ordered]@{
  TEMP                     = "$root\tmp"
  TMP                      = "$root\tmp"
  TMPDIR                   = "$root\tmp"
  PIP_CACHE_DIR            = "$root\cache\pip"
  UV_CACHE_DIR             = "$root\cache\uv"
  UV_PYTHON_INSTALL_DIR    = "$root\cache\uv-python"
  HF_HOME                  = "$root\cache\hf"
  HF_HUB_CACHE             = "$root\cache\hf\hub"
  TRANSFORMERS_CACHE       = "$root\cache\hf\transformers"
  TORCH_HOME               = "$root\cache\torch"
  XDG_CACHE_HOME           = "$root\cache\xdg"
  NPM_CONFIG_CACHE         = "$root\cache\npm"
  PLAYWRIGHT_BROWSERS_PATH = "$root\cache\playwright"
  PYTHONPYCACHEPREFIX      = "$root\cache\pycache"
  RUFF_CACHE_DIR           = "$root\cache\ruff"
  AGENTOPS_DATA_DIR        = "$root\data"
  AGENTOPS_ARTIFACTS_DIR   = "$root\artifacts"
  AGENTOPS_LOG_DIR         = "$root\logs"
  DUCKDB_TMP_DIR           = "$root\tmp\duckdb"
  VIRTUAL_ENV              = "$root\venv"
  UV_PROJECT_ENVIRONMENT   = "$root\venv"
}
foreach ($k in $map.Keys) {
  Set-Item -Path "env:$k" -Value $map[$k]
  if ($k -notin 'VIRTUAL_ENV','UV_PROJECT_ENVIRONMENT') { New-Item -ItemType Directory -Force -Path $map[$k] | Out-Null }
}
$env:PYTHONDONTWRITEBYTECODE = '0'
$env:AGENTOPS_MAX_MEMORY = '2GB'
if (Test-Path "$root\venv\Scripts") { $env:PATH = "$root\venv\Scripts;" + $env:PATH }
