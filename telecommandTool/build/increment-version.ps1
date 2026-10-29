param(
    [Parameter(Mandatory = $true)]
    [string]$IndexPath
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $IndexPath)) { throw "Missing frontend page: $IndexPath" }
$content = [IO.File]::ReadAllText($IndexPath)
$pattern = '(class="header-version">[^<]*?V)(\d+)\.(\d+)\.(\d+)(</p>)'
$match = [regex]::Match($content, $pattern)
if (-not $match.Success) { throw 'Cannot find a VMAJOR.MINOR.PATCH version in the header.' }
$patch = [long]::Parse($match.Groups[4].Value) + 1
$version = '{0}.{1}.{2}' -f $match.Groups[2].Value, $match.Groups[3].Value, $patch
$replacement = '{0}{1}{2}' -f $match.Groups[1].Value, $version, $match.Groups[5].Value
$content = $content.Substring(0, $match.Index) + $replacement + $content.Substring($match.Index + $match.Length)
[IO.File]::WriteAllText($IndexPath, $content, [Text.UTF8Encoding]::new($false))
Write-Host "Updated application version to V$version"
