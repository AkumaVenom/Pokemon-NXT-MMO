# Native tests for the actual PowerShell helpers. No Pester/download/install needed.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'Build\bootstrap_lib.ps1')
$script:checks = 0
function Assert-NxtEqual($Actual,$Expected,[string]$Name) {
    if ($Actual -cne $Expected) { throw "$Name failed: expected [$Expected], received [$Actual]" }
    $script:checks++
}
function Assert-NxtThrows([scriptblock]$Code,[string]$Name) {
    $thrown=$false
    try { & $Code | Out-Null } catch { $thrown=$true }
    if (-not $thrown) { throw "$Name did not reject unsafe input" }
    $script:checks++
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('NXT bootstrap (test) ' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temp)
try {
    foreach ($file in @('Build\bootstrap_lib.ps1','Build\bootstrap_windows.ps1')) {
        $tokens=$null; $parseErrors=$null
        [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $root $file),[ref]$tokens,[ref]$parseErrors)
        Assert-NxtEqual $parseErrors.Count 0 "PowerShell syntax: $file"
    }
    Assert-NxtEqual (ConvertTo-NxtArgument '') '""' 'Empty argument'
    Assert-NxtEqual (ConvertTo-NxtArgument '--no-open') '--no-open' 'Flag argument'
    Assert-NxtEqual (ConvertTo-NxtArgument 'C:\NXT (source)\file.py') '"C:\NXT (source)\file.py"' 'Space/parenthesis quoting'
    Assert-NxtEqual (ConvertTo-NxtArgument 'a"b') '"a\"b"' 'Embedded quote'
    Assert-NxtEqual (ConvertTo-NxtArgument 'C:\with space\') '"C:\with space\\"' 'Trailing slash quoting'
    Assert-NxtEqual (ConvertFrom-NxtGoVersion 'go version go1.27.1 windows/amd64') '1.27.1' 'Stable Go'
    foreach ($text in @('go version go1.22.9 windows/amd64','go version go1.27rc1 windows/amd64','go version go1.27.1 linux/amd64','go version go1.27.1 windows/386','garbage')) {
        Assert-NxtEqual (ConvertFrom-NxtGoVersion $text) $null "Invalid Go: $text"
    }
    $manifest=Read-NxtManifest (Join-Path $root 'Build\toolchains.json')
    Assert-NxtEqual $manifest.schema 1 'Manifest'
    foreach ($url in @('http://www.python.org/a.exe','https://www.python.org.evil.example/a.exe','https://evil.example/a.exe','https://user:pass@www.python.org/a.exe','file:///C:/python.exe','https://www.python.org:8443/a.exe')) {
        Assert-NxtThrows { Assert-NxtUrl $url } "Rejected URL: $url"
    }
    Assert-NxtEqual ((Assert-NxtUrl $manifest.go.url).Scheme) 'https' 'Official Go URL'
    $data=[pscustomobject]@{ implementation='cpython'; bits=64; machine='AMD64'; version='3.13.15'; release='final'; free_threaded=$false; executable='C:\Python\python.exe' }
    Assert-NxtEqual (Test-NxtPythonData $data) $true 'Compatible Python'
    $data.bits=32
    Assert-NxtEqual (Test-NxtPythonData $data) $false 'Wrong Python architecture'
    $data.bits=64; $data.free_threaded=$true
    Assert-NxtEqual (Test-NxtPythonData $data) $false 'Experimental free-threaded Python'
    $data.free_threaded=$false; $data.version='3.10.9'
    Assert-NxtEqual (Test-NxtPythonData $data) $false 'Old Python'
    $data.version='3.15.0'
    Assert-NxtEqual (Test-NxtPythonData $data) $false 'Unvalidated future Python minor'
    foreach ($name in @('../escape.exe','go/../../escape.exe','/absolute.exe','C:\escape.exe','go/file:stream','go/../escape','go/ambiguous. /x')) {
        Assert-NxtThrows { Get-NxtZipTarget $temp $name } "ZIP traversal: $name"
    }
    $safe=Get-NxtZipTarget $temp 'go/bin/go.exe'
    Assert-NxtEqual $safe ([IO.Path]::GetFullPath((Join-Path $temp 'go\bin\go.exe'))) 'Safe ZIP path'
    $sample=Join-Path $temp 'sample.bin'; [IO.File]::WriteAllText($sample,'abc')
    Assert-NxtEqual (Test-NxtHash $sample 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') $true 'Correct SHA-256'
    Assert-NxtEqual (Test-NxtHash $sample ('0'*64)) $false 'Wrong SHA-256'
    Assert-NxtEqual (Test-NxtHash (Join-Path $temp 'missing') ('0'*64)) $false 'Missing cached download'
    Assert-NxtThrows { Get-NxtDownload -Tool $manifest.go -Cache $temp -Offline } 'Offline cache miss'
    # Child-scope helpers and mocks disappear on exit; the real native-process
    # test below still uses the original implementation. No SDK is executed and
    # no download/installation is performed, even if this machine has Go already.
    & {
        . (Join-Path $root 'Build\bootstrap_lib.ps1')
        $savedEnvironment = @{}
        foreach ($name in @('NXT_GO','PATH','ProgramFiles','LOCALAPPDATA')) {
            $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name,'Process')
        }
        $userProfileBefore = $HOME
        $mockState = [pscustomobject]@{ Downloads=0; Extractions=0; ArchiveVersion=$manifest.go.version; CommandExecutable=$null }
        function New-NxtFakeGoSdk([string]$Directory,[string]$Version) {
            foreach ($relative in @('bin','src\runtime','pkg\tool\windows_amd64')) {
                [void][IO.Directory]::CreateDirectory((Join-Path $Directory $relative))
            }
            $fakeExecutable = Join-Path $Directory 'bin\go.exe'
            [IO.File]::WriteAllText($fakeExecutable,"go version go$Version windows/amd64")
            [IO.File]::WriteAllText((Join-Path $Directory 'pkg\tool\windows_amd64\compile.exe'),'fake compiler')
            return $fakeExecutable
        }
        function Invoke-NxtProcess {
            param([string]$File,[string[]]$Arguments,[switch]$Capture,[int]$TimeoutSeconds=30)
            if (-not $Capture -or $Arguments.Count -ne 1 -or $Arguments[0] -cne 'version') {
                throw 'Unexpected native command in Go discovery regression tests.'
            }
            return [pscustomobject]@{ ExitCode=0; Stdout=[IO.File]::ReadAllText($File); Stderr='' }
        }
        function Get-Command {
            [CmdletBinding()]
            param([string]$Name,[string]$CommandType)
            if ($Name -cne 'go.exe' -or $CommandType -cne 'Application') {
                throw 'Unexpected command lookup in Go discovery regression tests.'
            }
            if ($mockState.CommandExecutable) {
                return [pscustomobject]@{ Source=$mockState.CommandExecutable }
            }
            return $null
        }
        function Get-NxtDownload {
            param($Tool,[string]$Cache,[switch]$Offline)
            if ($Offline) { throw 'Offline discovery must not request a download.' }
            $mockState.Downloads++
            return (Join-Path $temp 'fake-go-archive.zip')
        }
        function Expand-NxtGoArchive {
            param([string]$Archive,[string]$Destination)
            $mockState.Extractions++
            [void](New-NxtFakeGoSdk (Join-Path $Destination 'go') $mockState.ArchiveVersion)
        }
        try {
            $env:NXT_GO = $null
            $env:PATH = Join-Path $temp 'empty-path'
            $env:ProgramFiles = Join-Path $temp 'program-files'
            $env:LOCALAPPDATA = Join-Path $temp 'local-app-data'
            $sdkDirectory = Join-Path $temp 'installed-sdk'
            $sdkExecutable = New-NxtFakeGoSdk $sdkDirectory $manifest.go.version
            $found = Test-NxtGo $sdkExecutable
            Assert-NxtEqual ($null -ne $found) $true 'Complete Go SDK accepted (reserved HOME regression)'
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($sdkExecutable)) 'Probed Go executable'
            Assert-NxtEqual $found.Version $manifest.go.version 'Probed Go version'
            Assert-NxtEqual (Test-NxtGo (Join-Path $temp 'missing-go.exe')) $null 'Missing Go executable rejected'
            Remove-Item -LiteralPath (Join-Path $sdkDirectory 'src\runtime') -Recurse -Force
            Assert-NxtEqual (Test-NxtGo $sdkExecutable) $null 'Go runtime sources required'
            [void](New-NxtFakeGoSdk $sdkDirectory $manifest.go.version)
            Remove-Item -LiteralPath (Join-Path $sdkDirectory 'pkg\tool\windows_amd64\compile.exe') -Force
            Assert-NxtEqual (Test-NxtGo $sdkExecutable) $null 'Go compiler tool required'
            [void](New-NxtFakeGoSdk $sdkDirectory '1.22.9')
            Assert-NxtEqual (Test-NxtGo $sdkExecutable) $null 'Unsupported Go version rejected by SDK probe'
            [void](New-NxtFakeGoSdk $sdkDirectory $manifest.go.version)

            $userCache = Join-Path $temp 'go-user-cache'
            $installedExecutable = New-NxtFakeGoSdk (Join-Path $env:ProgramFiles 'Go') $manifest.go.version
            $found = Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($installedExecutable)) 'Installed Go discovered offline'
            $mockState.CommandExecutable = $sdkExecutable
            $found = Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($sdkExecutable)) 'PATH Go discovered offline'
            $mockState.CommandExecutable = $null
            $env:NXT_GO = $sdkExecutable
            $found = Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($sdkExecutable)) 'Explicit Go override wins over installed SDK'
            $env:NXT_GO = Join-Path $temp 'invalid-override.exe'
            Assert-NxtThrows { Get-NxtGo -Manifest $manifest -UserCache $userCache } 'Invalid explicit Go override rejected'
            Assert-NxtEqual $mockState.Downloads 0 'Installed and override discovery never download'
            $env:NXT_GO = $null
            Remove-Item -LiteralPath (Join-Path $env:ProgramFiles 'Go') -Recurse -Force
            Assert-NxtThrows { Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline } 'Offline Go discovery miss'
            Assert-NxtEqual $mockState.Downloads 0 'Offline Go discovery never downloads'

            # Validate staging and publication using real filesystem moves. A
            # rejected archive must leave an existing incomplete cache intact.
            $cachedDirectory = Join-Path $userCache ("Toolchains\go" + $manifest.go.version)
            [void][IO.Directory]::CreateDirectory($cachedDirectory)
            $cacheMarker = Join-Path $cachedDirectory 'preserve.txt'
            [IO.File]::WriteAllText($cacheMarker,'previous cache')
            $mockState.ArchiveVersion = '1.23.0'
            Assert-NxtThrows { Get-NxtGo -Manifest $manifest -UserCache $userCache } 'Wrong archive version rejected before publication'
            Assert-NxtEqual ([IO.File]::ReadAllText($cacheMarker)) 'previous cache' 'Rejected archive preserves existing cache'
            Assert-NxtEqual (@(Get-ChildItem -LiteralPath (Split-Path -Parent $cachedDirectory) -Filter 'go-extract-*').Count) 0 'Rejected archive staging removed'
            $mockState.ArchiveVersion = $manifest.go.version
            $found = Get-NxtGo -Manifest $manifest -UserCache $userCache
            $cachedExecutable = Join-Path $cachedDirectory 'go\bin\go.exe'
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($cachedExecutable)) 'Validated SDK published into user cache'
            Assert-NxtEqual $found.Version $manifest.go.version 'Published SDK matches manifest'
            Assert-NxtEqual $mockState.Downloads 2 'Exactly one download attempt per staged install'
            Assert-NxtEqual $mockState.Extractions 2 'Exactly one extraction per staged install'
            $found = Get-NxtGo -Manifest $manifest -UserCache $userCache -Offline
            Assert-NxtEqual $found.Path ([IO.Path]::GetFullPath($cachedExecutable)) 'Cached Go reused offline'
            Assert-NxtEqual $mockState.Downloads 2 'Cached reuse does not download'
            Assert-NxtEqual $mockState.Extractions 2 'Cached reuse does not extract again'
            Assert-NxtEqual $HOME $userProfileBefore 'PowerShell HOME remains unchanged'
        } finally {
            foreach ($name in $savedEnvironment.Keys) {
                [Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process')
            }
        }
    }
    # Verify no native shell interprets spaces, quotes or ampersands in arguments.
    $ps=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $probe=Join-Path $temp 'argument probe.ps1'
    [IO.File]::WriteAllText($probe,'$args | ConvertTo-Json -Compress')
    $result=Invoke-NxtProcess -File $ps -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',$probe,'a b','C:\path (x)\','& untouched') -Capture
    Assert-NxtEqual $result.ExitCode 0 'Native process exit'
    $arguments=$result.Stdout | ConvertFrom-Json
    Assert-NxtEqual $arguments[0] 'a b' 'Native space argument'
    Assert-NxtEqual $arguments[1] 'C:\path (x)\' 'Native trailing backslash'
    Assert-NxtEqual $arguments[2] '& untouched' 'Native metacharacter'
    Write-Host "BOOTSTRAP HELPER TESTS PASSED: $script:checks checks"
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
