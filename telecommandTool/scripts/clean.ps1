$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$projectPrefix = $projectRoot.TrimEnd('\') + '\'
# Only these reproducible outputs are eligible. Source, offline wheels and releases stay.
$relativeTargets = @('build', 'build-fixed', 'build-win7', '__pycache__', 'tests\__pycache__', 'TelecommandTool.spec', 'dist\TelecommandTool-fixed.exe')
foreach ($relativeTarget in $relativeTargets) {
    $targetPath = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $relativeTarget))
    if (-not $targetPath.StartsWith($projectPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Cleanup target is outside project: $targetPath"
    }
    if (-not (Test-Path -LiteralPath $targetPath)) { continue }
    $item = Get-Item -LiteralPath $targetPath -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to clean a link: $targetPath"
    }
    if ($item.PSIsContainer) {
        $links = Get-ChildItem -LiteralPath $targetPath -Force -Recurse | Where-Object { $_.Attributes -band [System.IO.FileAttributes]::ReparsePoint }
        if ($links) { throw "Refusing to clean directory containing links: $targetPath" }
    }
    if ($relativeTarget -eq 'dist\TelecommandTool-fixed.exe') {
        $releasePath = Join-Path $projectRoot 'dist\TelecommandTool.exe'
        if (-not (Test-Path -LiteralPath $releasePath)) {
            Write-Warning 'Keeping fixed executable: standard release is missing.'
            continue
        }
        if ((Get-FileHash -LiteralPath $targetPath).Hash -ne (Get-FileHash -LiteralPath $releasePath).Hash) {
            Write-Warning 'Keeping fixed executable: it differs from the standard release.'
            continue
        }
    }
    try {
        Remove-Item -LiteralPath $targetPath -Recurse -Force -ErrorAction Stop
        Write-Host "Removed: $relativeTarget"
    } catch {
        if ($relativeTarget -eq 'dist\TelecommandTool-fixed.exe') {
            Write-Warning 'Fixed executable is in use. Close it and rerun this script.'
        } else { throw }
    }
}
