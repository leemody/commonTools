param(
    [string]$PythonPath = $env:TELECOMMAND_WIN7_PYTHON
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$projectRoot = Split-Path -Parent $PSScriptRoot
$originalPath = $env:PATH
Push-Location -LiteralPath $projectRoot
try {
    # Explicit parameter / environment variable takes precedence over discovery.
    if (-not $PythonPath) {
        $localPython = Join-Path $projectRoot '.build-env-py38\python.exe'
        $existingPython = 'D:\PythonLandControl\telecommandTool\.build-env-py38\python.exe'
        if (Test-Path -LiteralPath $localPython) {
            $PythonPath = $localPython
        } elseif (Test-Path -LiteralPath $existingPython) {
            $PythonPath = $existingPython
        } elseif (Get-Command py -ErrorAction SilentlyContinue) {
            $detected = & py -3.8 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $PythonPath = "$detected".Trim() }
        }
        if (-not $PythonPath) { $PythonPath = 'python' }
    }

    $info = & $PythonPath -B -c "import sys, struct, json; print(json.dumps(dict(executable=sys.executable, version=list(sys.version_info[:3]), bits=struct.calcsize('P')*8, platform=sys.platform)))"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect Python. Use -PythonPath to select Python 3.8 x64.' }
    $runtime = ($info -join "`n") | ConvertFrom-Json
    if ($runtime.platform -ne 'win32' -or $runtime.version[0] -ne 3 -or $runtime.version[1] -ne 8 -or $runtime.bits -ne 64) {
        throw 'Win7 x64 build requires Windows Python 3.8 (64-bit). Use -PythonPath or TELECOMMAND_WIN7_PYTHON.'
    }
    $PythonPath = $runtime.executable
    Write-Host "Win7 build Python: $PythonPath"
    # Conda keeps OpenSSL DLLs in Library\bin; search this runtime before host tools.
    $runtimeDir = Split-Path -Parent $PythonPath
    $env:PATH = "$runtimeDir;$(Join-Path $runtimeDir 'Library\bin');$(Join-Path $runtimeDir 'Scripts');$originalPath"
    & $PythonPath -B -c "import PyInstaller; assert PyInstaller.__version__ == '5.13.2', PyInstaller.__version__"
    if ($LASTEXITCODE -ne 0) { throw "Install the pinned builder: & '$PythonPath' -m pip install pyinstaller==5.13.2" }

    # Importing and testing with the target interpreter catches runtime incompatibilities.
    & $PythonPath -B -c "import sys; sys.path.insert(0, 'src'); import web_server, low_speed_telecommand_frame_generator, time_schedule_telecommand_frame_generator, direct_command_frame_generator, high_speed_frame_generator, high_speed_idle_frame_generator"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.8 application import check failed.' }
    & $PythonPath -B -m unittest discover -s src/tests -t src -v
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed; packaging aborted.' }

    $indexPath = Join-Path $projectRoot 'frontend\index.html'
    if (-not (Test-Path -LiteralPath $indexPath)) { throw 'Missing index.html.' }
    $frontendPath = Join-Path $projectRoot 'frontend'
    if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'image.png'))) { throw 'Missing image.png.' }
    $versionUpdater = Join-Path $PSScriptRoot 'increment-version.ps1'
    & $versionUpdater -IndexPath $indexPath
    & $PythonPath -B -m PyInstaller --noconfirm --clean --onefile --console --noupx `
        --name TelecommandTool-Win7-x64 --distpath dist --workpath build/work-win7 `
        --specpath build/spec-win7 --add-data "$frontendPath;frontend" src/web_server.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }

    $exePath = Join-Path $projectRoot 'dist\TelecommandTool-Win7-x64.exe'
    if (-not (Test-Path -LiteralPath $exePath)) { throw 'Build did not produce the executable.' }
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src') -Filter '*.py')
    $sources += Get-ChildItem -LiteralPath $frontendPath -File
    $sources += Get-Item -LiteralPath (Join-Path $PSScriptRoot 'build-win7.ps1')
    $sources += Get-Item -LiteralPath $versionUpdater
    $sourceHashes = @{}
    foreach ($source in $sources) {
        $sourceHashes[$source.Name] = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
    }
    $manifest = [ordered]@{
        built_at = (Get-Date).ToString('o')
        target = 'Windows 7 SP1 x64'
        python = ($runtime.version -join '.')
        pyinstaller = '5.13.2'
        executable = 'TelecommandTool-Win7-x64.exe'
        sha256 = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash
        source_sha256 = $sourceHashes
        validation = 'Python 3.8 import and regression tests passed; target OS acceptance required.'
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $projectRoot 'dist\TelecommandTool-Win7-x64.build.json') -Encoding UTF8
    Write-Host "Built: $exePath"
    Write-Host 'Target: Windows 7 SP1 x64. Verify startup and browser operation on the target PC.'
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
