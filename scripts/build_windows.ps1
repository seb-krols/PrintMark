# Run from the repository root in PowerShell. Requires Python 3.12, uv and Inno Setup 6.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    # Windows PowerShell 5.1 turns redirected native stderr (uv/pyinstaller progress) into
    # terminating errors under 'Stop'; rely on the exit code instead.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Program @Arguments 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $env:UV_PYTHON = '3.12'
    Invoke-Checked uv @('sync', '--frozen', '--extra', 'dev')
    Invoke-Checked uv @('run', 'ruff', 'check', '.')
    Invoke-Checked uv @('run', 'ruff', 'format', '--check', '.')
    Invoke-Checked uv @('run', 'pytest')
    # One folder (dist/basemark) holding basemark.exe, basemark-desktop.exe and their runtime.
    Invoke-Checked uv @('run', 'pyinstaller', '--noconfirm', '--clean', 'scripts/basemark-windows.spec')
    Invoke-Checked uv @('run', 'python', 'scripts/package_release.py', 'windows-x64')
    $version = (& uv run python -c 'from basemark import __version__; print(__version__)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read package version' }
    $payload = Join-Path (Get-Location) 'build/windows-payload'
    if (Test-Path $payload) { Remove-Item $payload -Recurse -Force }
    Expand-Archive "dist/basemark-$version-windows-x64.zip" $payload
    # Machine-wide and per-user (winget --scope user) Inno Setup installs, then PATH.
    $compiler = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Inno Setup 6/ISCC.exe')
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (!$compiler) {
        $onPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($onPath) { $compiler = $onPath.Source }
    }
    if (!$compiler) { throw 'Install Inno Setup 6 to build the Windows installer.' }
    Invoke-Checked $compiler @("/DAppVersion=$version", "scripts/windows_installer.iss")
    $setup = "dist/basemark-$version-windows-x64-setup.exe"
    $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    # LF endings so `sha256sum -c` also works on macOS/Linux.
    [IO.File]::WriteAllText((Join-Path (Get-Location) "$setup.sha256"), "$hash  $(Split-Path $setup -Leaf)`n")
    Write-Host "Built and verified portable ZIP and installer in dist/"
} finally {
    Pop-Location
}
