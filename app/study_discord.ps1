param([ValidateSet('start','restore')][string]$Mode, [ValidateSet('','online','idle','dnd','invisible')][string]$Previous = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$scope = [System.Windows.Automation.TreeScope]::Descendants
$condition = [System.Windows.Automation.Condition]::TrueCondition
function Nodes($root) { return $root.FindAll($scope, $condition) }
function Invoke-Control($node) {
    $pattern = $null
    if ($node.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); return }
    if ($node.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $pattern.Select(); return }
    if ($node.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { $pattern.Expand(); return }
    throw 'The Discord control cannot be invoked through accessibility.'
}
function Has-Submenu($node) {
    $pattern = $null
    return $node.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)
}
function Status($name) {
    if ($name -match '(?i)do not disturb|\bdnd\b') { return 'dnd' }
    if ($name -match '(?i)invisible') { return 'invisible' }
    if ($name -match '(?i)idle') { return 'idle' }
    if ($name -match '(?i)online') { return 'online' }
    return ''
}
$prior = $Previous
$invoked = $false
try {
    $process = Get-Process Discord,DiscordPTB,DiscordCanary -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $process) { throw 'Open Discord desktop to let Brain manage DND.' }
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
    $profile = @(Nodes $root) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -match '(?i)(set status|your profile|user profile|user status)' } | Select-Object -First 1
    if (-not $profile) { throw 'Discord status controls are unavailable. Open Discord with accessibility enabled and retry.' }
    $current = Status $profile.Current.Name
    Invoke-Control $profile
    Start-Sleep -Milliseconds 250
    $nodes = @(Nodes $root)
    $statusButton = $nodes | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem -and (Status $_.Current.Name) -and (Has-Submenu $_) } | Select-Object -First 1
    if (-not $current -and $statusButton) { $current = Status $statusButton.Current.Name }
    if ($statusButton) { Invoke-Control $statusButton; Start-Sleep -Milliseconds 250 }
    if (-not $current) { throw 'Could not identify the previous Discord status; no status was changed.' }
    if ($Mode -eq 'restore' -and $current -ne 'dnd') {
        @{state='unchanged';message='Discord status was changed manually; Brain left it as chosen.'} | ConvertTo-Json -Compress
        exit 0
    }
    if ($Mode -eq 'start') { $prior = $current }
    $target = if ($Mode -eq 'start') { 'dnd' } else { $Previous }
    if (-not $target) { throw 'No previous Discord status was recorded.' }
    $targetNode = @(Nodes $root) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem -and (Status $_.Current.Name) -eq $target } | Select-Object -First 1
    if (-not $targetNode) { throw 'Discord status menu is unavailable. Select the status manually.' }
    Invoke-Control $targetNode
    $invoked = $true
    Start-Sleep -Milliseconds 250
    $verified = @(Nodes $root) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -match '(?i)(set status|your profile|user profile|user status)' -and (Status $_.Current.Name) -eq $target } | Select-Object -First 1
    if (-not $verified) {
        # Some Discord versions expose current status only inside the profile menu.
        Invoke-Control $profile
        Start-Sleep -Milliseconds 250
        $verified = @(Nodes $root) | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::MenuItem -and (Status $_.Current.Name) -eq $target -and (Has-Submenu $_) } | Select-Object -First 1
        Invoke-Control $profile
    }
    if (-not $verified) { throw 'Discord did not confirm the status change; check the status in Discord.' }
    @{state=$(if ($Mode -eq 'start') {'dnd'} else {'restored'});previous=$current;message=$(if ($Mode -eq 'start') {'Discord is on Do Not Disturb.'} else {'Previous Discord status restored.'})} | ConvertTo-Json -Compress
} catch {
    @{state=$(if ($invoked) {'unverified'} else {'unavailable'});previous=$prior;message=$_.Exception.Message} | ConvertTo-Json -Compress
}
