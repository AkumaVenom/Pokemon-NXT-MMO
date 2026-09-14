# Windows PowerShell 5.1-compatible. Dot-sourcing only defines functions.
# All executable downloads are pinned and verified before extraction/execution.
Set-StrictMode -Version 2.0

function ConvertTo-NxtArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW / C-runtime quoting; never cmd.exe /c.
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-NxtProcess {
    param([string]$File, [string[]]$Arguments = @(), [switch]$Capture,
          [int]$TimeoutSeconds = 30)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $File
    $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-NxtArgument $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = [bool]$Capture
    $info.RedirectStandardOutput = [bool]$Capture
    $info.RedirectStandardError = [bool]$Capture
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        if (-not $process.Start()) { throw "Cannot start $File" }
        if ($Capture) {
            $stdout = $process.StandardOutput.ReadToEndAsync()
            $stderr = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                $process.Kill()
                $process.WaitForExit()
                throw "Tool probe timed out: $File"
            }
            $process.WaitForExit()
            return [pscustomobject]@{ ExitCode=$process.ExitCode; Stdout=$stdout.Result; Stderr=$stderr.Result }
        }
        # Install/build children keep their console and finish naturally. No hidden
        # background installer is left behind by an arbitrary build timeout.
        $process.WaitForExit()
        return [pscustomobject]@{ ExitCode=$process.ExitCode; Stdout=''; Stderr='' }
    }
    finally { $process.Dispose() }
}

function Test-NxtPythonData {
    param($Data)
    try {
        return ($Data.implementation -eq 'cpython' -and $Data.bits -eq 64 -and
            $Data.machine -match '^(AMD64|x86_64)$' -and
            [version]$Data.version -ge [version]'3.11.0' -and
            [version]$Data.version -lt [version]'3.15.0' -and
            $Data.release -eq 'final' -and -not $Data.free_threaded -and
            -not [string]::IsNullOrWhiteSpace($Data.executable))
    } catch { return $false }
}

function Test-NxtPython {
    param([string]$File)
    if ([string]::IsNullOrWhiteSpace($File) -or -not (Test-Path -LiteralPath $File -PathType Leaf)) { return $null }
    # Never execute Store aliases, which can open a Store window instead of Python.
    if ($File -match '[\\/]Microsoft[\\/]WindowsApps[\\/]') { return $null }
    $code = "import sys,struct,json,platform,sysconfig,ssl,venv,ensurepip,sqlite3,tkinter,_tkinter; print(json.dumps(dict(executable=sys.executable,version=platform.python_version(),implementation=sys.implementation.name,bits=struct.calcsize('P')*8,machine=platform.machine(),release=sys.version_info.releaselevel,free_threaded=bool(sysconfig.get_config_var('Py_GIL_DISABLED')))))"
    try {
        $result = Invoke-NxtProcess -File $File -Arguments @('-I','-c',$code) -Capture
        if ($result.ExitCode -ne 0) { return $null }
        $data = $result.Stdout.Trim() | ConvertFrom-Json
        if (-not (Test-NxtPythonData $data)) { return $null }
        return [pscustomobject]@{ Path=[string]$data.executable; Version=[string]$data.version }
    } catch { return $null }
}

function ConvertFrom-NxtGoVersion {
    param([string]$Text)
    $match = [regex]::Match($Text.Trim(), '^go version go(\d+\.\d+(?:\.\d+)?) windows/amd64$')
    if (-not $match.Success) { return $null }
    $version = [version]$match.Groups[1].Value
    if ($version -lt [version]'1.23') { return $null }
    return $match.Groups[1].Value
}

function Test-NxtGo {
    param([string]$File)
    if ([string]::IsNullOrWhiteSpace($File) -or -not (Test-Path -LiteralPath $File -PathType Leaf)) { return $null }
    try {
        $result = Invoke-NxtProcess -File $File -Arguments @('version') -Capture
        if ($result.ExitCode -ne 0) { return $null }
        $version = ConvertFrom-NxtGoVersion $result.Stdout
        if ($null -eq $version) { return $null }
        # PowerShell variable names are case-insensitive; HOME is read-only.
        $goInstallRoot = Split-Path -Parent (Split-Path -Parent $File)
        if (-not (Test-Path -LiteralPath (Join-Path $goInstallRoot 'src\runtime') -PathType Container)) { return $null }
        if (-not (Test-Path -LiteralPath (Join-Path $goInstallRoot 'pkg\tool\windows_amd64\compile.exe') -PathType Leaf)) { return $null }
        return [pscustomobject]@{ Path=[IO.Path]::GetFullPath($File); Version=$version }
    } catch { return $null }
}

function Assert-NxtUrl {
    param([string]$Url)
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or -not $uri.IsDefaultPort -or
        $uri.UserInfo -or $uri.Fragment -or $uri.Query -or
        $uri.DnsSafeHost -notin @('www.python.org','python.org','dl.google.com','go.dev')) {
        throw 'Tool download is not an approved official HTTPS URL.'
    }
    return $uri
}

function Read-NxtManifest {
    param([string]$Path)
    $data = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($data.schema -ne 1) { throw 'Unsupported toolchain manifest schema.' }
    foreach ($name in @('python','go')) {
        $tool = $data.$name
        if ($tool.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw "Invalid $name SHA-256 in toolchain manifest." }
        if ($tool.version -notmatch '^\d+\.\d+\.\d+$') { throw "Invalid $name version in manifest." }
        $uri = Assert-NxtUrl $tool.url
        if ([IO.Path]::GetFileName($uri.AbsolutePath) -cne $tool.filename) { throw 'Tool filename does not match URL.' }
        if ($name -eq 'python') {
            if ($tool.version -notmatch '^3\.13\.\d+$' -or $tool.filename -cne "python-$($tool.version)-amd64.exe" -or
                $uri.DnsSafeHost -ne 'www.python.org' -or $uri.AbsolutePath -cne "/ftp/python/$($tool.version)/$($tool.filename)" -or
                $tool.publisher -cne 'Python Software Foundation') { throw 'Invalid Python installer declaration.' }
        } else {
            if ([version]$tool.version -lt [version]'1.23.0' -or $tool.filename -cne "go$($tool.version).windows-amd64.zip" -or
                $uri.DnsSafeHost -ne 'dl.google.com' -or $uri.AbsolutePath -cne "/go/$($tool.filename)") { throw 'Invalid Go archive declaration.' }
        }
    }
    return $data
}

function Test-NxtHash {
    param([string]$Path, [string]$Expected)
    if ($Expected -notmatch '^[0-9a-fA-F]{64}$' -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ieq $Expected)
}

function Save-NxtHttpFile {
    param([string]$Url, [string]$Destination)
    $uri = Assert-NxtUrl $Url
    for ($redirect=0; $redirect -le 5; $redirect++) {
        $request = [Net.HttpWebRequest]::Create($uri)
        $request.AllowAutoRedirect = $false
        $request.Timeout = 120000
        $request.ReadWriteTimeout = 120000
        $request.UserAgent = 'Pokemon-NXT-MMO-Build/1.3.4'
        if ($null -ne $request.Proxy) { $request.Proxy.Credentials = [Net.CredentialCache]::DefaultCredentials }
        $response = $null
        try {
            $response = $request.GetResponse()
            $status = [int]$response.StatusCode
            if ($status -ge 300 -and $status -lt 400) {
                $next = New-Object Uri -ArgumentList $uri, ([string]$response.Headers['Location'])
                $uri = Assert-NxtUrl $next.AbsoluteUri
                continue
            }
            if ($status -ne 200) { throw "Download returned HTTP $status." }
            if ($response.ContentLength -gt 268435456) { throw 'Tool archive exceeds the 256 MiB limit.' }
            $inputStream = $response.GetResponseStream()
            $outputStream = [IO.File]::Open($Destination, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $buffer = New-Object byte[] 131072
                [long]$total = 0
                $watch = [Diagnostics.Stopwatch]::StartNew()
                $last = 0.0
                while (($count = $inputStream.Read($buffer,0,$buffer.Length)) -gt 0) {
                    $total += $count
                    if ($total -gt 268435456 -or $watch.Elapsed.TotalMinutes -gt 20) { throw 'Tool download exceeded its size/time limit.' }
                    $outputStream.Write($buffer,0,$count)
                    if ($watch.Elapsed.TotalSeconds - $last -ge 3) {
                        Write-Host ('  Downloaded {0:N1} MiB...' -f ($total/1MB))
                        $last = $watch.Elapsed.TotalSeconds
                    }
                }
                if ($total -eq 0 -or ($response.ContentLength -ge 0 -and $total -ne $response.ContentLength)) { throw 'Download was incomplete.' }
            } finally { $outputStream.Dispose(); $inputStream.Dispose() }
            return
        } finally { if ($null -ne $response) { $response.Dispose() } }
    }
    throw 'Too many tool download redirects.'
}

function Get-NxtDownload {
    param($Tool, [string]$Cache, [switch]$Offline)
    [void][IO.Directory]::CreateDirectory($Cache)
    $path = Join-Path $Cache $Tool.filename
    if (Test-NxtHash $path $Tool.sha256) {
        Write-Host "Verified cached download: $($Tool.filename)"
        return $path
    }
    if ($Offline) { throw "Offline mode: a verified $($Tool.filename) download is not cached. Run BUILD_ALL.bat normally once online." }
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    $partial = $path + '.partial'
    for ($attempt=1; $attempt -le 3; $attempt++) {
        try {
            Write-Host "Downloading $($Tool.filename) from $($Tool.url) [attempt $attempt/3]"
            Save-NxtHttpFile -Url $Tool.url -Destination $partial
            if (-not (Test-NxtHash $partial $Tool.sha256)) { throw 'SHA-256 mismatch. The download will NOT be executed or unpacked.' }
            [IO.File]::Move($partial,$path)
            Write-Host 'SHA-256 verification passed.'
            return $path
        } catch {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            Write-Host $_.Exception.Message
            if ($attempt -eq 3) { throw 'Tool download failed. Check the network/proxy and the bootstrap log, then rerun the BAT. No unverified tool was used.' }
            Start-Sleep -Seconds (2*$attempt)
        }
    }
}

function Get-NxtZipTarget {
    param([string]$Root, [string]$Name)
    $normal = $Name.Replace('\','/')
    if ([string]::IsNullOrWhiteSpace($normal) -or $normal.StartsWith('/') -or $normal.Contains(':')) { throw 'Unsafe ZIP entry.' }
    foreach ($segment in $normal.Split('/')) {
        if ($segment -eq '..' -or $segment -eq '.' -or $segment -match '[. ]$') { throw 'Unsafe ZIP traversal or ambiguous Windows name.' }
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    $target = [IO.Path]::GetFullPath((Join-Path $base $normal))
    if (-not $target.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)) { throw 'ZIP entry leaves extraction folder.' }
    return $target
}

function Expand-NxtGoArchive {
    param([string]$Archive, [string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [void][IO.Directory]::CreateDirectory($Destination)
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        if ($zip.Entries.Count -gt 50000) { throw 'Too many entries in Go archive.' }
        [long]$total = 0
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $zip.Entries) {
            if (-not $entry.FullName.StartsWith('go/',[StringComparison]::Ordinal)) { throw 'Unexpected top-level Go archive path.' }
            $target = Get-NxtZipTarget $Destination $entry.FullName
            if (-not $seen.Add($target)) { throw 'Duplicate case-insensitive ZIP entry.' }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Symlinks are not permitted in the tool archive.' }
            $total += $entry.Length
            if ($total -gt 1073741824) { throw 'Unpacked Go archive exceeds 1 GiB.' }
            if ($entry.FullName.EndsWith('/')) { [void][IO.Directory]::CreateDirectory($target) }
            else {
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $target))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$false)
            }
        }
    } finally { $zip.Dispose() }
}

function Get-NxtPythonCandidates {
    param([string]$ManagedPython)
    $items = New-Object 'System.Collections.Generic.List[string]'
    $items.Add($ManagedPython)
    foreach ($command in @(Get-Command python.exe,python3.exe -CommandType Application -ErrorAction SilentlyContinue)) { $items.Add($command.Source) }
    foreach ($base in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore')) {
        foreach ($key in @(Get-ChildItem -LiteralPath $base -ErrorAction SilentlyContinue | Sort-Object PSChildName -Descending)) {
            $install = Join-Path $key.PSPath 'InstallPath'
            $item = Get-Item -LiteralPath $install -ErrorAction SilentlyContinue
            if ($null -ne $item) {
                $executable = [string]$item.GetValue('ExecutablePath')
                $directory = [string]$item.GetValue('')
                if ($executable) { $items.Add($executable) }
                if ($directory) { $items.Add((Join-Path $directory 'python.exe')) }
            }
        }
    }
    foreach ($version in @('313','314','312','311')) {
        if ($env:LOCALAPPDATA) { $items.Add((Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe")) }
        if ($env:ProgramFiles) { $items.Add((Join-Path $env:ProgramFiles "Python$version\python.exe")) }
    }
    return $items | Select-Object -Unique
}

function Get-NxtPython {
    param($Manifest, [string]$UserCache, [string]$LogDirectory, [switch]$Offline)
    # Full installer keeps Tk, SSL, venv and pip. Do not use the embeddable ZIP.
    $target = Join-Path $env:LOCALAPPDATA 'Programs\PokemonNXT\Python313'
    $managed = Join-Path $target 'python.exe'
    if ($env:NXT_PYTHON) {
        $found = Test-NxtPython $env:NXT_PYTHON
        if ($null -eq $found) { throw 'NXT_PYTHON points to an unusable interpreter. Clear the override for automatic setup, or select standard x64 CPython 3.11-3.14 with pip/venv/Tk.' }
        Write-Host "Using explicit Python: $($found.Path)"
        return $found
    }
    foreach ($candidate in @(Get-NxtPythonCandidates $managed)) {
        $found = Test-NxtPython $candidate
        if ($null -ne $found) { Write-Host "Using Python $($found.Version): $($found.Path)"; return $found }
    }
    if ($Offline) { throw 'Offline mode: no compatible Python installation was found. Run the BAT normally online first.' }
    $installer = Get-NxtDownload -Tool $Manifest.python -Cache (Join-Path $UserCache 'Downloads')
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or
        $signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false) -cne $Manifest.python.publisher) {
        throw 'Python installer signature is not valid for Python Software Foundation. Installation stopped. Do not disable signature verification.'
    }
    Write-Host "Installing Python $($Manifest.python.version) for your Windows user: $target"
    Write-Host 'The normal Python installer registers this per-user installation. No system PATH, file associations, or existing world configuration is changed.'
    $installerLog = Join-Path $LogDirectory ('python-install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $arguments = @('/quiet','/norestart','InstallAllUsers=0',"TargetDir=$target",'Include_exe=1','Include_lib=1',
        'Include_pip=1','Include_tcltk=1','Include_launcher=0','InstallLauncherAllUsers=0',
        'Include_test=0','Include_doc=0','Include_dev=0','Include_debug=0','Include_symbols=0',
        'Include_freethreaded=0','Shortcuts=0','AssociateFiles=0','PrependPath=0','AppendPath=0','/log',$installerLog)
    $result = Invoke-NxtProcess -File $installer -Arguments $arguments
    if ($result.ExitCode -notin @(0,3010)) { throw "Python installer exited with code $($result.ExitCode). See $installerLog. An existing incomplete Python install may need repair through Windows Installed apps." }
    # A registered installer may retain an existing location. Re-discover it rather
    # than assuming success means the requested directory was used.
    foreach ($candidate in @(Get-NxtPythonCandidates $managed)) {
        $found = Test-NxtPython $candidate
        if ($null -ne $found) {
            if ($result.ExitCode -eq 3010) { Write-Host 'Python requested a restart; its interpreter currently passes the build checks.' }
            return $found
        }
    }
    throw "Python installed but failed its x64/SSL/pip/venv/Tk check. Review $installerLog and restart Windows if requested."
}

function Get-NxtGo {
    param($Manifest, [string]$UserCache, [switch]$Offline)
    $goCacheRoot = Join-Path $UserCache ("Toolchains\go" + $Manifest.go.version)
    $executable = Join-Path $goCacheRoot 'go\bin\go.exe'
    if ($env:NXT_GO) {
        $found = Test-NxtGo $env:NXT_GO
        if ($null -eq $found) { throw 'NXT_GO points to an unusable compiler. Clear the override for automatic setup or select a complete Windows x64 Go 1.23+ installation.' }
        Write-Host "Using explicit Go: $($found.Path)"
        return $found
    }
    $candidates = @($executable)
    $command = Get-Command go.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $command) { $candidates += $command.Source }
    foreach ($base in @($env:ProgramFiles,$env:LOCALAPPDATA)) {
        if ($base) { $candidates += (Join-Path $base 'Go\bin\go.exe'); $candidates += (Join-Path $base 'Programs\Go\bin\go.exe') }
    }
    foreach ($candidate in $candidates) {
        $found = Test-NxtGo $candidate
        if ($null -ne $found) { Write-Host "Using Go $($found.Version): $($found.Path)"; return $found }
    }
    if ($Offline) { throw 'Offline mode: no complete Go installation was found. Run the BAT normally online first.' }
    $archive = Get-NxtDownload -Tool $Manifest.go -Cache (Join-Path $UserCache 'Downloads')
    $parent = Split-Path -Parent $goCacheRoot
    [void][IO.Directory]::CreateDirectory($parent)
    $stage = Join-Path $parent ('go-extract-' + [guid]::NewGuid().ToString('N'))
    try {
        Write-Host 'Unpacking the verified Go compiler into the per-user tool cache...'
        Expand-NxtGoArchive -Archive $archive -Destination $stage
        $check = Test-NxtGo (Join-Path $stage 'go\bin\go.exe')
        if ($null -eq $check -or [version]$check.Version -ne [version]$Manifest.go.version) { throw 'Unpacked Go compiler failed its version/completeness check.' }
        if (Test-Path -LiteralPath $goCacheRoot) {
            [IO.Directory]::Move($goCacheRoot,($goCacheRoot + '.previous-' + [guid]::NewGuid().ToString('N')))
        }
        [IO.Directory]::Move($stage,$goCacheRoot)
    } finally { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
    $found = Test-NxtGo $executable
    if ($null -eq $found) { throw 'Installed Go compiler could not be started.' }
    return $found
}
