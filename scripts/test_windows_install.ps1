# Exercise the installed app and upgrade/uninstall without using the runner's real config.
# It shares the real install's uninstall entry and startup shortcut: on a lab PC, run it
# before (re)installing BaseMark itself.
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
    # /CONNECT=no keeps the real PrusaSlicer untouched.
    $options = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/DIR=`"$install`"", '/CONNECT=no')
    # Not -Wait: that also waits for the export check the installer leaves running.
    $p = Start-Process $setup -ArgumentList $options -PassThru; $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
    $binary = Join-Path $install 'basemark.exe'
    # The installer starts the background export check and adds it to the user's startup.
    function Get-Watcher {
        Get-CimInstance Win32_Process -Filter "Name = 'basemark-desktop.exe'" |
            Where-Object { $_.CommandLine -like '*--watch*' -and $_.ExecutablePath -like "$install*" }
    }
    $watcher = $null
    for ($i = 0; $i -lt 40 -and !$watcher; $i++) { Start-Sleep -Milliseconds 250; $watcher = Get-Watcher }
    if (!$watcher) { throw 'Background export check was not started' }
    $startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'BaseMark export check.lnk'
    if (!(Test-Path $startup)) { throw 'Export check is not started at login' }
    # Part numbers on, so the counter and audit log are exercised too.
    $config = Join-Path $env:APPDATA 'BaseMark/config.toml'
    New-Item (Split-Path $config) -ItemType Directory -Force | Out-Null
    [IO.File]::WriteAllText($config, "config_version = 2`ntemplate = `"{material} {id}`"`n")
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
    $before = @(Get-Watcher).ProcessId
    $p = Start-Process $setup -ArgumentList $options -PassThru; $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw 'Upgrade failed' }
    Start-Sleep -Seconds 2
    $after = @(Get-Watcher)
    if ($after.Count -ne 1 -or $before -contains $after[0].ProcessId) {
        throw 'Upgrade did not replace the export check with exactly one new copy'
    }
    $p = Start-Process (Join-Path $install 'unins000.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -PassThru; $p.WaitForExit()
    if ($p.ExitCode -ne 0 -or (Test-Path $binary)) { throw 'Uninstall failed' }
    if (Get-Watcher) { throw 'Export check still running after uninstall' }
    if (Test-Path $startup) { throw 'Startup entry left after uninstall' }
    if ((Get-FileHash $state).Hash -ne $stateHash -or (Get-FileHash $log).Hash -ne $logHash -or (Get-FileHash $config).Hash -ne $configHash) {
        throw 'Upgrade/uninstall altered settings or audit history'
    }
    Write-Host 'Installed executable, desktop launch, upgrade and uninstall verified.'
} finally {
    $env:APPDATA = $originalAppData
}
