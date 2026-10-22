$ErrorActionPreference = 'Stop'
$brainRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$notes = Join-Path $brainRoot 'personal-notes'
if (-not (Test-Path -LiteralPath $notes)) { throw "Notes folder missing: $notes" }

$claudeHome = Join-Path $env:USERPROFILE '.claude'
New-Item -ItemType Directory -Force -Path $claudeHome | Out-Null
$settingsFile = Join-Path $claudeHome 'settings.json'
if (Test-Path -LiteralPath $settingsFile) {
    $config = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
} else {
    $config = [pscustomobject]@{}
}
if (-not $config.PSObject.Properties['hooks']) { $config | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{}) }

function Add-BrainHook($eventName, $command, $timeout, $matcher) {
    if (-not $config.hooks.PSObject.Properties[$eventName]) {
        $config.hooks | Add-Member -NotePropertyName $eventName -NotePropertyValue @()
    }
    $installed = @($config.hooks.$eventName | ForEach-Object { $_.hooks } | Where-Object { $_.command -eq $command })
    if ($installed) { return }
    $entry = [pscustomobject]@{ hooks = @(@{ type = 'command'; command = $command; timeout = $timeout }) }
    if ($matcher) { $entry | Add-Member -NotePropertyName matcher -NotePropertyValue $matcher }
    $config.hooks.$eventName = @($config.hooks.$eventName) + $entry
}
Add-BrainHook 'SessionStart' "py `"$(Join-Path $brainRoot 'brain_session_hook.py')`"" 30 'startup|resume'
$saveCommand = "py `"$(Join-Path $brainRoot 'brain_save_session.py')`""
Add-BrainHook 'Stop' $saveCommand 10 $null
Add-BrainHook 'SessionEnd' $saveCommand 3 $null

# Let sessions started in other project folders write the notes.
if (-not $config.PSObject.Properties['permissions']) { $config | Add-Member -NotePropertyName permissions -NotePropertyValue ([pscustomobject]@{}) }
if (-not $config.permissions.PSObject.Properties['additionalDirectories']) { $config.permissions | Add-Member -NotePropertyName additionalDirectories -NotePropertyValue @() }
if (@($config.permissions.additionalDirectories) -notcontains $notes) {
    $config.permissions.additionalDirectories = @($config.permissions.additionalDirectories) + $notes
}
$json = $config | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($settingsFile, $json + "`n", (New-Object System.Text.UTF8Encoding $false))

$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Brain Daily.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'powershell.exe'
$launcher = Join-Path $brainRoot 'bin\brain-daily.ps1'
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$shortcut.WorkingDirectory = $brainRoot
$shortcut.WindowStyle = 7
$shortcut.Description = 'Open personal Brain and Claude Code at sign-in'
$shortcut.Save()
Write-Output "Installed Brain startup shortcut: $shortcutPath"
Write-Output "Installed Claude Code Brain hooks: $settingsFile"
