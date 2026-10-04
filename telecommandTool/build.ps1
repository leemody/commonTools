$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onefile --console --name TelecommandTool --workpath build --specpath build --distpath dist --add-data "$PSScriptRoot\index.html;." web_server.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }
Write-Host "已生成 $PSScriptRoot\dist\TelecommandTool.exe"
