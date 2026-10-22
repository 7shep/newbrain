$ErrorActionPreference = 'Stop'
$brainRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$notes = Join-Path $brainRoot 'personal-notes'
$env:BRAIN_NOTES = $notes
Remove-Item Env:TERM -ErrorAction SilentlyContinue
Set-Location -LiteralPath $notes

$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) {
    Write-Host 'Claude Code is missing. Install it from https://claude.com/claude-code' -ForegroundColor Red
    return
}
Write-Host "Brain notes: $notes"
Write-Host 'Claude Code will load the Brain session hook and inbox now.'
& $claude
