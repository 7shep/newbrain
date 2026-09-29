$ErrorActionPreference = 'Stop'
$brainRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$notes = Join-Path $brainRoot 'personal-notes'
$url = 'http://127.0.0.1:4747/'
$healthy = $false
try {
    $page = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2).Content
    $healthy = $page.Contains('"__NOTES_ROOT__"') -eq $false -and $page.Contains('personal-notes')
} catch {}

if (-not $healthy) {
    $py = (Get-Command py -ErrorAction Stop).Source
    $server = Join-Path $brainRoot 'app\server.py'
    Start-Process -FilePath $py -ArgumentList @($server, '--notes', $notes, '--port', '4747', '--no-open') -WorkingDirectory $brainRoot -WindowStyle Hidden | Out-Null
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        try {
            $page = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1).Content
            if ($page.Contains('personal-notes')) { $healthy = $true; break }
        } catch {}
    }
}
if (-not $healthy) { throw 'Brain did not start on port 4747. Check whether another program is using that port.' }

Start-Process $url
$terminal = Join-Path $brainRoot 'bin\brain-terminal.ps1'
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$terminal`"") -WorkingDirectory $notes
