# Entry point used by BUILD_ALL.bat. No Python or Go is needed to run this file.
# Process-local execution policy only; corporate policy and OS protections remain.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$buildArguments = @($args)
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$logDirectory = Join-Path $root '.build\logs'
$transcript = $false
$lock = $null
$resultCode = 1
try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem -or
        $env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -or $PSVersionTable.PSVersion -lt [version]'5.1') {
        throw 'Use Windows 10/11 x64 and Windows PowerShell 5.1. The BAT selects the 64-bit Windows host automatically.'
    }
    if (-not $env:LOCALAPPDATA) { throw 'The Windows user LOCALAPPDATA folder is unavailable.' }
    foreach ($required in @('Build\build.py','Build\bootstrap_lib.ps1','Build\toolchains.json','Server\requirements.txt','Client\launcher\go.mod')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $required) -PathType Leaf)) { throw "Missing $required. Extract the entire source ZIP first." }
    }
    [void][IO.Directory]::CreateDirectory($logDirectory)
    $logPath = Join-Path $logDirectory ('bootstrap-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.log')
    Start-Transcript -LiteralPath $logPath -Force | Out-Null
    $transcript = $true
    . (Join-Path $PSScriptRoot 'bootstrap_lib.ps1')
    $manifest = Read-NxtManifest (Join-Path $PSScriptRoot 'toolchains.json')
    $offline = $buildArguments -contains '--no-install'
    # Reject unsupported flags before installing anything. --root belongs to the
    # Python developer entry point; the BAT always builds its own source directory.
    foreach ($argument in $buildArguments) {
        if ($argument -notin @('--no-install','--no-open','--existing-environment','--help','-h')) {
            throw "Unknown build option: $argument. Supported: --no-install, --no-open, --existing-environment, --help."
        }
    }
    if ($buildArguments -contains '--help' -or $buildArguments -contains '-h') {
        Write-Host 'BUILD_ALL.bat [--no-open] [--no-install]'
        Write-Host 'Normal mode automatically installs missing Python/Go and isolated packages.'
        Write-Host '--no-install requires existing tools and the exact build dependencies; no downloads.'
        Write-Host '--existing-environment is developer-only verification without production package pins.'
        $resultCode = 0
    } else {
        if ($offline -and $buildArguments -contains '--existing-environment') { throw '--no-install and --existing-environment cannot be combined.' }
        $userCache = Join-Path $env:LOCALAPPDATA 'PokemonNXT'
        [void][IO.Directory]::CreateDirectory($userCache)
        # Locks include prerequisite setup and the complete build. A second source
        # copy for this user cannot race installation of the shared compiler.
        try { $lock = [IO.File]::Open((Join-Path $userCache 'bootstrap.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
        catch { throw 'Another Pokemon NXT automatic build is running for this Windows user. Close or finish it before starting another.' }
        if ((New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($root))).AvailableFreeSpace -lt 2GB) { throw 'Less than 2 GiB is free on the source drive. Free disk space before building.' }
        if ((New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($userCache))).AvailableFreeSpace -lt 1GB) { throw 'Less than 1 GiB is free on the Windows user tool-cache drive.' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $env:PYTHONUTF8 = '1'
        $env:PYTHONIOENCODING = 'utf-8'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        foreach ($key in @('PYTHONHOME','PYTHONPATH','PYLAUNCHER_ALLOW_INSTALL','PYLAUNCHER_ALWAYS_INSTALL','GOROOT','GOOS','GOARCH','GOFLAGS','GOEXPERIMENT')) { [Environment]::SetEnvironmentVariable($key,$null,'Process') }
        $env:GOTOOLCHAIN = 'local'
        $env:GOENV = 'off'
        $env:GOWORK = 'off'
        Write-Host ''
        Write-Host '[Prerequisites 1/3] Find or install full Python x64 with pip, venv and Tk'
        $python = Get-NxtPython -Manifest $manifest -UserCache $userCache -LogDirectory $logDirectory -Offline:$offline
        Write-Host '[Prerequisites 2/3] Find or install the Go Windows x64 compiler'
        $go = Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline:$offline
        $env:NXT_PYTHON = $python.Path
        $env:NXT_GO = $go.Path
        # Only this process and its children see these PATH additions.
        $pythonDirectory = Split-Path -Parent $python.Path
        $env:PATH = $pythonDirectory + ';' + (Join-Path $pythonDirectory 'Scripts') + ';' + (Split-Path -Parent $go.Path) + ';' + $env:PATH
        $record = [ordered]@{ version=$manifest.bootstrap_version; python=$python.Version; go=$go.Version; user_cache=$userCache; downloaded_tools_verified_with='SHA-256; Python additionally requires PSF Authenticode'; offline=[bool]$offline }
        $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root '.build\bootstrap.json') -Encoding UTF8
        Write-Host '[Prerequisites 3/3] Install isolated Python packages, test, compile and package'
        Write-Host 'Tool setup completed. Continuing automatically; no second BAT run is needed.'
        $buildCommand = @('-u',(Join-Path $PSScriptRoot 'build.py'),'--root',$root) + $buildArguments
        $buildResult = Invoke-NxtProcess -File $python.Path -Arguments $buildCommand
        $resultCode = $buildResult.ExitCode
    }
} catch {
    Write-Host ''
    Write-Host ('AUTOMATIC BUILD FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Your configured server, database, game source and previous builds were not replaced.'
    Write-Host ('Logs: ' + $logDirectory)
    $resultCode = 1
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
    if ($transcript) { Stop-Transcript | Out-Null }
}
exit $resultCode
