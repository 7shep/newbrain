$ErrorActionPreference = 'Stop'
$brainRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$notes = Join-Path $brainRoot 'personal-notes'
$env:BRAIN_NOTES = $notes
Remove-Item Env:TERM -ErrorAction SilentlyContinue
Set-Location -LiteralPath $notes

$codex = (Get-Command codex.cmd -ErrorAction SilentlyContinue).Source
if (-not $codex) {
    $candidate = Join-Path $env:APPDATA 'npm\codex.cmd'
    if (Test-Path -LiteralPath $candidate) { $codex = $candidate }
}
if (-not $codex) {
    Write-Host 'Codex CLI is missing. Install it with: npm install -g @openai/codex' -ForegroundColor Red
    return
}
Write-Host "Brain notes: $notes"
Write-Host 'Codex will load the Brain session hook and inbox now.'
& $codex
