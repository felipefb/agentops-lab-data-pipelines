# Stores the Anthropic and OpenRouter API keys as USER environment variables (Windows registry, HKCU).
# Keys are typed hidden, never echoed, and never written to the repository or to any file.
# Usage (in your own PowerShell window):  powershell -ExecutionPolicy Bypass -File E:\AgentOpsLab\repo\scripts\set_llm_keys.ps1
$ErrorActionPreference = 'Stop'

function Read-Secret([string]$prompt) {
    $sec = Read-Host -Prompt $prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$keys = [ordered]@{
    ANTHROPIC_API_KEY  = @{ prompt = 'Anthropic API key (sk-ant-...) - Enter para pular';  prefix = 'sk-ant-' }
    OPENROUTER_API_KEY = @{ prompt = 'OpenRouter API key (sk-or-...) - Enter para pular'; prefix = 'sk-or-' }
}

foreach ($name in $keys.Keys) {
    $v = (Read-Secret $keys[$name].prompt).Trim()
    if (-not $v) { Write-Host "$name : mantido como esta"; continue }
    if (-not $v.StartsWith($keys[$name].prefix)) {
        Write-Warning "$name nao comeca com '$($keys[$name].prefix)'. Salvo mesmo assim; confira se colou a chave certa."
    }
    [Environment]::SetEnvironmentVariable($name, $v, 'User')   # persistente para novos processos
    Set-Item -Path "env:$name" -Value $v                      # disponivel nesta janela
    Write-Host ("{0} : salvo ({1} caracteres, termina em ...{2})" -f $name, $v.Length, $v.Substring($v.Length - 4))
    $v = $null
}

# Quick connectivity check without printing secrets (no tokens spent: lists models only).
if ($env:ANTHROPIC_API_KEY) {
    try {
        $r = Invoke-RestMethod -Uri 'https://api.anthropic.com/v1/models?limit=1' -Headers @{
            'x-api-key' = $env:ANTHROPIC_API_KEY; 'anthropic-version' = '2023-06-01' }
        Write-Host "Anthropic: OK (API respondeu)"
    } catch { Write-Warning "Anthropic: falhou -> $($_.Exception.Message)" }
}
if ($env:OPENROUTER_API_KEY) {
    try {
        $r = Invoke-RestMethod -Uri 'https://openrouter.ai/api/v1/key' -Headers @{ Authorization = "Bearer $env:OPENROUTER_API_KEY" }
        Write-Host "OpenRouter: OK (chave valida)"
    } catch { Write-Warning "OpenRouter: falhou -> $($_.Exception.Message)" }
}
Write-Host "`nFeche e reabra o terminal (ou o Claude Code) para que novos processos vejam as variaveis."
