$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$versionUpdater = Join-Path $PSScriptRoot 'increment-version.ps1'
$version = & $versionUpdater -IndexPath (Join-Path $projectRoot 'frontend\index.html')
$exeName = "TelecommandTool-V$version"
python -m PyInstaller --noconfirm --clean --onefile --console --name $exeName --workpath build/work --specpath build/spec --distpath dist --add-data "$projectRoot\frontend;frontend" src/web_server.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }
$exePath = Join-Path $projectRoot ('dist\' + $exeName + '.exe')
Write-Host "Built: $exePath"
