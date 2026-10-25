# Exercise the installed app and upgrade/uninstall without using the runner's real config.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$originalAppData = $env:APPDATA
$scratch = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$trial = Join-Path $scratch ('BaseMark lab ' + [char]0x00E9 + ' ' + [guid]::NewGuid())
$install = Join-Path $trial 'Installed app'
$env:APPDATA = Join-Path $trial 'User data'
New-Item $trial -ItemType Directory -Force | Out-Null
try {
    $setup = (Get-ChildItem dist/basemark-*-windows-x64-setup.exe | Select-Object -Last 1).FullName
    $options = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$install`"")
    $p = Start-Process $setup -ArgumentList $options -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
    $binary = Join-Path $install 'basemark.exe'
    $config = Join-Path $env:APPDATA 'BaseMark/config.toml'
    New-Item (Split-Path $config -Parent) -ItemType Directory -Force | Out-Null
    'counter_prefix = "T"' | Set-Content $config -Encoding utf8
    $configHash = (Get-FileHash $config).Hash
    $job = Join-Path $trial 'Lab coupon.gcode'
    Copy-Item tests/fixtures/prusaslicer-2.8.1-petg-relative.gcode $job
    & $binary --mode auto $job
    if ($LASTEXITCODE -ne 0) { throw 'Installed executable failed' }
    if (!(Get-Content $job -First 1).StartsWith('; BASEMARK stamp')) { throw 'No stamp produced' }
    # The export returned above while its corner notice keeps running in its own process.
    $notice = $null
    for ($i = 0; $i -lt 40 -and !$notice; $i++) {
        Start-Sleep -Milliseconds 250
        $notice = Get-CimInstance Win32_Process -Filter "Name = 'basemark-desktop.exe'" |
            Where-Object { $_.CommandLine -like '*--notify stamped*' }
    }
    if (!$notice) { throw 'Export notice was not started' }
    $notice | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    $state = Join-Path $env:APPDATA 'BaseMark/counter.json'
    $log = Join-Path $env:APPDATA 'BaseMark/log.csv'
    if ((Get-Content $state -Raw | ConvertFrom-Json).next -ne 2) { throw 'Counter did not advance' }
    $stateHash = (Get-FileHash $state).Hash
    $logHash = (Get-FileHash $log).Hash
    $desktop = Start-Process (Join-Path $install 'basemark-desktop.exe') -PassThru
    Start-Sleep -Seconds 12
    $desktop.Refresh()
    if ($desktop.HasExited) { throw 'Desktop settings launcher exited unexpectedly' }
    $settingsWindow = Get-Process basemark-desktop | Where-Object { $_.MainWindowTitle -eq 'BaseMark' }
    if (!$settingsWindow) { throw 'Desktop did not open its settings window' }
    # End the UI smoke process before testing an upgrade.
    taskkill /PID $desktop.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not close settings process' }
    $p = Start-Process $setup -ArgumentList $options -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw 'Upgrade failed' }
    $p = Start-Process (Join-Path $install 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
    if ($p.ExitCode -ne 0 -or (Test-Path $binary)) { throw 'Uninstall failed' }
    if ((Get-FileHash $state).Hash -ne $stateHash -or (Get-FileHash $log).Hash -ne $logHash -or (Get-FileHash $config).Hash -ne $configHash) {
        throw 'Upgrade/uninstall altered settings or audit history'
    }
    Write-Host 'Installed executable, desktop launch, upgrade and uninstall verified.'
} finally {
    $env:APPDATA = $originalAppData
}
