$ErrorActionPreference = 'Stop'
$brainRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$notes = Join-Path $brainRoot 'personal-notes'
if (-not (Test-Path -LiteralPath $notes)) { throw "Notes folder missing: $notes" }

$codexHome = Join-Path $env:USERPROFILE '.codex'
$hooksFile = Join-Path $codexHome 'hooks.json'
if (Test-Path -LiteralPath $hooksFile) {
    $config = Get-Content -LiteralPath $hooksFile -Raw | ConvertFrom-Json
} else {
    $config = [pscustomobject]@{}
}
if (-not $config.PSObject.Properties['hooks']) { $config | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{}) }
if (-not $config.hooks.PSObject.Properties['SessionStart']) { $config.hooks | Add-Member -NotePropertyName SessionStart -NotePropertyValue @() }
$hookScript = Join-Path $brainRoot 'brain_session_hook.py'
$command = "py `"$hookScript`""
$existing = @($config.hooks.SessionStart | ForEach-Object { $_.hooks } | Where-Object { $_.commandWindows -eq $command -or $_.command -eq $command })
if (-not $existing) {
    $config.hooks.SessionStart = @($config.hooks.SessionStart) + [pscustomobject]@{
        matcher = 'startup|resume'
        hooks = @(@{
            type = 'command'
            command = $command
            commandWindows = $command
            timeout = 30
            statusMessage = 'Loading Brain and Google Calendar'
        })
    }
}
$json = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($hooksFile, $json + "`n", (New-Object System.Text.UTF8Encoding $false))

$codexConfig = Join-Path $codexHome 'config.toml'
$settings = Get-Content -LiteralPath $codexConfig -Raw
if ($settings -notmatch '(?m)^\[sandbox_workspace_write\]\s*$') {
    $escapedNotes = $notes.Replace('\', '\\')
    Add-Content -LiteralPath $codexConfig -Value "`n[sandbox_workspace_write]`nwritable_roots = [`"$escapedNotes`"]`n" -Encoding UTF8
} elseif ($settings -notmatch [regex]::Escape($notes.Replace('\', '\\'))) {
    Write-Warning 'Add personal-notes to sandbox_workspace_write.writable_roots in Codex config.toml manually; an existing table needs review.'
}

$env:BRAIN_NOTES = $notes
& py (Join-Path $brainRoot 'brain_codex.py')

$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Brain Daily.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'powershell.exe'
$launcher = Join-Path $brainRoot 'bin\brain-daily.ps1'
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$shortcut.WorkingDirectory = $brainRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Open personal Brain and Codex at sign-in'
$shortcut.Save()
Write-Output "Installed Brain startup shortcut: $shortcutPath"
Write-Output "Installed Codex SessionStart hook: $hooksFile"
