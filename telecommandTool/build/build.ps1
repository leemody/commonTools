$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$versionUpdater = Join-Path $PSScriptRoot 'increment-version.ps1'
& $versionUpdater -IndexPath (Join-Path $projectRoot 'frontend\index.html')
python -m PyInstaller --noconfirm --clean --onefile --console --name TelecommandTool --workpath build/work --specpath build/spec --distpath dist --add-data "$projectRoot\frontend;frontend" src/web_server.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }
Write-Host "已生成 $projectRoot\dist\TelecommandTool.exe"
