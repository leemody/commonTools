param(
    [string]$PythonPath = "python"
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$version = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $version.Trim() -ne '3.8') {
    throw "Windows 7 兼容版必须使用 Python 3.8，当前版本为 $version。可通过 -PythonPath 指定 Python 3.8 的 python.exe。"
}

& $PythonPath -c "import PyInstaller; assert PyInstaller.__version__.startswith('5.13.'), PyInstaller.__version__"
if ($LASTEXITCODE -ne 0) {
    throw "请先使用该 Python 安装 PyInstaller 5.13.2：$PythonPath -m pip install pyinstaller==5.13.2"
}

$indexPath = Join-Path $PSScriptRoot 'index.html'
& $PythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name TelecommandTool-Win7-x64 `
    --distpath dist `
    --workpath build-win7 `
    --specpath build-win7 `
    --add-data "$indexPath;." `
    web_server.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码 $LASTEXITCODE" }
Write-Host "已生成 $PSScriptRoot\dist\TelecommandTool-Win7-x64.exe"
