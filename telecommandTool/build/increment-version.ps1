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

# Keep the standalone orbit-programming guide aligned with the application version.
$projectRoot = Split-Path -Parent $PSScriptRoot
$markdownGuide = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.md' | Where-Object {
    [IO.File]::ReadAllText($_.FullName).Contains('APID_0x0A3_')
} | Select-Object -First 1
if (-not $markdownGuide) { throw 'Cannot locate the orbit-programming Markdown guide.' }
$guidePaths = @(
    (Join-Path $projectRoot 'frontend\orbit-programming-guide.html'),
    $markdownGuide.FullName
)
foreach ($guidePath in $guidePaths) {
    if (-not (Test-Path -LiteralPath $guidePath)) { throw "Missing versioned guide: $guidePath" }
    $guideContent = [IO.File]::ReadAllText($guidePath)
    if ($guideContent -notmatch 'V\d+\.\d+\.\d+') { throw "Cannot find a version in guide: $guidePath" }
    $guideContent = [regex]::Replace($guideContent, 'V\d+\.\d+\.\d+', "V$version")
    if ($guidePath.EndsWith('.html')) {
        $subtitlePattern = '(?s)(<header><h1>.*?</h1><p>).*?(</p></header>)'
        $guideContent = [regex]::Replace($guideContent, $subtitlePattern, [System.Text.RegularExpressions.MatchEvaluator]{
            param($item)
            $item.Groups[1].Value + "&#36866;&#29992;&#29256;&#26412; V$version &#183; &#31163;&#32447;&#24110;&#21161;&#39029;&#38754;" + $item.Groups[2].Value
        }, 1)
        $titlePattern = '(?s)(<title>.*?)(?:\s\?\s|\s&#183;\s)(V\d+\.\d+\.\d+)(</title>)'
        $guideContent = [regex]::Replace($guideContent, $titlePattern, [System.Text.RegularExpressions.MatchEvaluator]{
            param($item)
            $item.Groups[1].Value + ' &#183; ' + $item.Groups[2].Value + $item.Groups[3].Value
        }, 1)
    }
    [IO.File]::WriteAllText($guidePath, $guideContent, [Text.UTF8Encoding]::new($false))
}
Write-Host "Updated application and guide version to V$version"
Write-Output $version
