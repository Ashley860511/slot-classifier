<#
.SYNOPSIS
  Archive slot classifier outputs to the company AI survey fileserver.

.DESCRIPTION
  Copies one video's classifier output, reports, logs, and original video into
  the company network drive using Robocopy.

.EXAMPLE
  .\archive_to_fileserver.ps1 -VideoId "10" -GameName "Goal Rush"

.EXAMPLE
  .\archive_to_fileserver.ps1 -VideoId "WildCoaster" -GameName "WildCoaster"
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$VideoId,

    [Parameter(Mandatory=$true)]
    [string]$GameName,

    [string]$TargetRoot = "\\192.168.123.5\jl商用遊戲機事務處\JLRD01研發一部\JLRD03美術設計課\IGaming\0_Common\AI_survey"
)

$ErrorActionPreference = "Stop"

function Get-RelativePathText {
    param(
        [Parameter(Mandatory=$true)] [string]$BasePath,
        [Parameter(Mandatory=$true)] [string]$FullPath
    )
    $base = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $full = [System.IO.Path]::GetFullPath($FullPath)
    if ($full.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($base.Length)
    }
    return [System.IO.Path]::GetFileName($FullPath)
}

function Test-IsExcludedPath {
    param(
        [Parameter(Mandatory=$true)] [string]$BasePath,
        [Parameter(Mandatory=$true)] [string]$FullPath,
        [string[]]$ExcludedDirectories = @()
    )
    $relative = Get-RelativePathText -BasePath $BasePath -FullPath $FullPath
    $parts = $relative -split '[\\/]+'
    foreach ($part in $parts) {
        foreach ($excluded in $ExcludedDirectories) {
            if ($part -ieq $excluded) {
                return $true
            }
        }
    }
    return $false
}

function Get-IncludedFileCount {
    param(
        [Parameter(Mandatory=$true)] [string]$Path,
        [string[]]$ExcludedDirectories = @(),
        [string[]]$ExcludedExtensions = @()
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    $count = 0
    Get-ChildItem -LiteralPath $Path -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-IsExcludedPath -BasePath $Path -FullPath $_.FullName -ExcludedDirectories $ExcludedDirectories) {
            return
        }
        if ($ExcludedExtensions -contains $_.Extension.ToLowerInvariant()) {
            return
        }
        $count++
    }
    return $count
}

function Invoke-RobocopyWithProgress {
    param(
        [Parameter(Mandatory=$true)] [string]$Source,
        [Parameter(Mandatory=$true)] [string]$Destination,
        [Parameter(Mandatory=$true)] [string]$Activity,
        [string[]]$ExcludedDirectories = @(),
        [string[]]$ExcludedFiles = @("*.tmp")
    )

    $fileCount = Get-IncludedFileCount -Path $Source -ExcludedDirectories $ExcludedDirectories -ExcludedExtensions @(".tmp")
    Write-Progress -Activity $Activity -Status "準備複製 $fileCount 個檔案" -PercentComplete 5

    $args = @($Source, $Destination, "/E", "/R:2", "/W:2", "/NFL", "/NDL", "/NP")
    if ($ExcludedDirectories.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludedDirectories
    }
    if ($ExcludedFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludedFiles
    }

    Write-Progress -Activity $Activity -Status "Robocopy 複製中..." -PercentComplete 35
    & robocopy @args
    $copyCode = $LASTEXITCODE

    Write-Progress -Activity $Activity -Status "確認複製結果" -PercentComplete 90
    if ($copyCode -gt 7) {
        Write-Progress -Activity $Activity -Completed
        throw "$Activity 失敗，Robocopy exit code: $copyCode"
    }

    Write-Progress -Activity $Activity -Status "完成" -PercentComplete 100
    Start-Sleep -Milliseconds 250
    Write-Progress -Activity $Activity -Completed
}

function Copy-TopLevelFilesWithProgress {
    param(
        [Parameter(Mandatory=$true)] [string]$Source,
        [Parameter(Mandatory=$true)] [string]$Destination,
        [Parameter(Mandatory=$true)] [string]$Activity,
        [Parameter(Mandatory=$true)] [string[]]$Extensions
    )

    $files = @(Get-ChildItem -LiteralPath $Source -File -ErrorAction SilentlyContinue | Where-Object { $Extensions -contains $_.Extension.ToLowerInvariant() })
    $total = [Math]::Max(1, $files.Count)
    $index = 0

    foreach ($file in $files) {
        $index++
        $percent = [int](($index / $total) * 100)
        Write-Progress -Activity $Activity -Status $file.Name -PercentComplete $percent
        Copy-Item -LiteralPath $file.FullName -Destination $Destination -Force
    }
    Write-Progress -Activity $Activity -Completed
}

function Convert-HtmlAttributeValueForRegex {
    param(
        [Parameter(Mandatory=$true)] [string]$Value
    )
    return [System.Text.RegularExpressions.Regex]::Escape($Value)
}

function Copy-ReportHtmlWithBundledAssets {
    param(
        [Parameter(Mandatory=$true)] [string]$Source,
        [Parameter(Mandatory=$true)] [string]$Destination,
        [string]$AssetFolderName = "report_assets"
    )

    $htmlFiles = @(Get-ChildItem -LiteralPath $Source -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension.ToLowerInvariant() -eq ".html" })
    if ($htmlFiles.Count -eq 0) {
        return
    }

    $assetRoot = Join-Path $Destination $AssetFolderName
    New-Item -ItemType Directory -Force -Path $assetRoot | Out-Null

    $htmlTotal = [Math]::Max(1, $htmlFiles.Count)
    $htmlIndex = 0

    foreach ($html in $htmlFiles) {
        $htmlIndex++
        Write-Progress -Activity "整理 report HTML 與圖片資產" -Status $html.Name -PercentComplete ([int](($htmlIndex / $htmlTotal) * 100))

        $htmlText = Get-Content -LiteralPath $html.FullName -Raw -Encoding UTF8
        $matches = @([regex]::Matches($htmlText, '(?i)(?<attr>src|href)\s*=\s*(?<quote>["''])(?<ref>[^"'']+)(\k<quote>)'))
        $assetIndex = 0
        $assetMap = @{}

        foreach ($match in $matches) {
            $attr = $match.Groups["attr"].Value
            $quote = $match.Groups["quote"].Value
            $ref = $match.Groups["ref"].Value.Trim()
            if (-not $ref) { continue }

            if ($ref.StartsWith("#")) { continue }
            if ($ref -match '^(?i)(data:|https?:|mailto:|javascript:)') { continue }

            if ($ref -match '^(?i)file:.+\.html(#.+)?$') {
                $anchor = ""
                if ($ref -match '(#.+)$') {
                    $anchor = $Matches[1]
                }
                $old = Convert-HtmlAttributeValueForRegex -Value $match.Value
                $new = "$attr=$quote$anchor$quote"
                $htmlText = [regex]::Replace($htmlText, $old, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $new }, 1)
                continue
            }

            $cleanRef = ($ref -split '#')[0]
            $cleanRef = ($cleanRef -split '\?')[0]
            if (-not $cleanRef) { continue }

            try {
                $cleanRef = [System.Uri]::UnescapeDataString($cleanRef)
            } catch {
                # Keep original text when URL decoding fails.
            }

            $sourcePath = $null
            if ($cleanRef -match '^(?i)file:') {
                try {
                    $sourcePath = ([System.Uri]$cleanRef).LocalPath
                } catch {
                    continue
                }
            } else {
                $relativeRef = ($cleanRef -replace '/', '\').TrimStart('.', '\', '/')
                if ([System.IO.Path]::IsPathRooted($relativeRef)) { continue }
                if (($relativeRef -split '\\') -contains '..') { continue }
                $sourcePath = Join-Path $Source $relativeRef
            }

            if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { continue }

            $extension = [System.IO.Path]::GetExtension($sourcePath).ToLowerInvariant()
            if (@(".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp") -notcontains $extension) { continue }

            if (-not $assetMap.ContainsKey($sourcePath)) {
                $assetIndex++
                $safeName = "{0:D4}_{1}" -f $assetIndex, ([System.IO.Path]::GetFileName($sourcePath) -replace '[\\/:*?"<>|]', '_')
                $targetPath = Join-Path $assetRoot $safeName
                Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
                $assetMap[$sourcePath] = "$AssetFolderName/$safeName"
            }

            $newRef = $assetMap[$sourcePath]
            $old = Convert-HtmlAttributeValueForRegex -Value $match.Value
            $new = "$attr=$quote$newRef$quote"
            $htmlText = [regex]::Replace($htmlText, $old, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $new }, 1)
        }

        Set-Content -LiteralPath (Join-Path $Destination $html.Name) -Value $htmlText -Encoding UTF8
    }

    Write-Progress -Activity "整理 report HTML 與圖片資產" -Completed
}

function Copy-ReportReferencedAssetsWithProgress {
    param(
        [Parameter(Mandatory=$true)] [string]$Source,
        [Parameter(Mandatory=$true)] [string]$Destination
    )

    $htmlFiles = @(Get-ChildItem -LiteralPath $Source -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension.ToLowerInvariant() -eq ".html" })
    $references = New-Object System.Collections.Generic.HashSet[string]

    foreach ($html in $htmlFiles) {
        $htmlText = Get-Content -LiteralPath $html.FullName -Raw
        $matches = [regex]::Matches($htmlText, '(?i)(?:src|href)\s*=\s*["'']([^"'']+)["'']')
        foreach ($match in $matches) {
            $ref = $match.Groups[1].Value.Trim()
            if (-not $ref) { continue }
            if ($ref.StartsWith('#')) { continue }
            if ($ref -match '^(?i)(data:|https?:|mailto:|javascript:)') { continue }
            if ($ref -match '^(?i)file:') { continue }

            $cleanRef = ($ref -split '#')[0]
            $cleanRef = ($cleanRef -split '\?')[0]
            if (-not $cleanRef) { continue }

            try {
                $cleanRef = [System.Uri]::UnescapeDataString($cleanRef)
            } catch {
                # Keep original text when URL decoding fails.
            }

            $cleanRef = $cleanRef -replace '/', '\'
            if ([System.IO.Path]::IsPathRooted($cleanRef)) { continue }
            if (($cleanRef -split '\\') -contains '..') { continue }
            [void]$references.Add($cleanRef)
        }
    }

    $refs = @($references | Sort-Object)
    $total = [Math]::Max(1, $refs.Count)
    $index = 0

    foreach ($ref in $refs) {
        $index++
        $percent = [int](($index / $total) * 100)
        Write-Progress -Activity "複製 HTML 引用圖片" -Status $ref -PercentComplete $percent

        $sourcePath = Join-Path $Source $ref
        if (-not (Test-Path -LiteralPath $sourcePath)) { continue }

        $targetPath = Join-Path $Destination $ref
        $targetParent = Split-Path -Parent $targetPath
        if ($targetParent) {
            New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
        }

        if (Test-Path -LiteralPath $sourcePath -PathType Container) {
            Invoke-RobocopyWithProgress `
                -Source $sourcePath `
                -Destination $targetPath `
                -Activity "複製 HTML 引用資料夾：$ref" `
                -ExcludedDirectories @()
        } else {
            Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
        }
    }

    Write-Progress -Activity "複製 HTML 引用圖片" -Completed
}

function Copy-OriginalVideosWithProgress {
    param(
        [Parameter(Mandatory=$true)] [string]$InputVideoDir,
        [Parameter(Mandatory=$true)] [string]$Destination,
        [Parameter(Mandatory=$true)] [string]$VideoId,
        [Parameter(Mandatory=$true)] [string]$GameName
    )

    if (-not (Test-Path -LiteralPath $InputVideoDir)) {
        Write-Warning "找不到原始影片資料夾：$InputVideoDir"
        return @()
    }

    $videoExtensions = @(".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
    $allVideos = @(Get-ChildItem -LiteralPath $InputVideoDir -File -ErrorAction SilentlyContinue |
        Where-Object { $videoExtensions -contains $_.Extension.ToLowerInvariant() })

    $videos = @($allVideos | Where-Object {
        $_.BaseName -ieq $VideoId -or $_.BaseName -ieq $GameName
    })

    if ($videos.Count -eq 0) {
        $safeGameName = $GameName -replace '[\\/:*?"<>|]', '_'
        $videos = @($allVideos | Where-Object {
            $_.BaseName -ieq $safeGameName
        })
    }

    if ($videos.Count -eq 0) {
        Write-Warning "找不到對應的原始影片：VideoId=$VideoId, GameName=$GameName"
        return @()
    }

    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $total = [Math]::Max(1, $videos.Count)
    $index = 0
    $copied = @()

    foreach ($video in $videos) {
        $index++
        $percent = [int](($index / $total) * 100)
        Write-Progress -Activity "複製原始影片" -Status $video.Name -PercentComplete $percent
        Copy-Item -LiteralPath $video.FullName -Destination $Destination -Force
        $copied += $video.FullName
    }

    Write-Progress -Activity "複製原始影片" -Completed
    return $copied
}

function Copy-ReportAssetsWithProgress {
    param(
        [Parameter(Mandatory=$true)] [string]$Source,
        [Parameter(Mandatory=$true)] [string]$Destination
    )

    $assetDirs = @()
    $htmlFiles = @(Get-ChildItem -LiteralPath $Source -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension.ToLowerInvariant() -eq ".html" })

    foreach ($html in $htmlFiles) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($html.Name)
        foreach ($candidateName in @("$baseName`_files", "$baseName.files", "report_files")) {
            $candidate = Join-Path $Source $candidateName
            if (Test-Path -LiteralPath $candidate) {
                $assetDirs += Get-Item -LiteralPath $candidate
            }
        }
    }

    foreach ($candidateName in @("assets", "images", "report_files")) {
        $candidate = Join-Path $Source $candidateName
        if (Test-Path -LiteralPath $candidate) {
            $assetDirs += Get-Item -LiteralPath $candidate
        }
    }

    $assetDirs = @($assetDirs | Sort-Object FullName -Unique)
    $total = [Math]::Max(1, $assetDirs.Count)
    $index = 0

    foreach ($dir in $assetDirs) {
        $index++
        $percent = [int](($index / $total) * 100)
        $targetDir = Join-Path $Destination $dir.Name
        Write-Progress -Activity "複製報告附屬圖片" -Status $dir.Name -PercentComplete $percent
        Invoke-RobocopyWithProgress `
            -Source $dir.FullName `
            -Destination $targetDir `
            -Activity "複製報告附屬圖片：$($dir.Name)" `
            -ExcludedDirectories @()
    }

    Write-Progress -Activity "複製報告附屬圖片" -Completed
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$SafeGameName = $GameName -replace '[\\/:*?"<>|]', '_'
$TargetBase = Join-Path $TargetRoot $SafeGameName
$TargetReport = Join-Path $TargetBase "01_report"
$TargetImages = Join-Path $TargetBase "02_classified_images"
$TargetLogs = Join-Path $TargetBase "03_logs"
$TargetVideo = Join-Path $TargetBase "video"

$SourceOutput = Join-Path $Root "project\output\$VideoId"
$SourceInputVideos = Join-Path $Root "project\input_videos"

if (-not (Test-Path -LiteralPath $SourceOutput)) {
    throw "找不到分類輸出資料夾：$SourceOutput"
}

if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "找不到公司網路磁碟路徑，請確認 VPN / 網路磁碟權限：$TargetRoot"
}

New-Item -ItemType Directory -Force -Path $TargetReport | Out-Null
New-Item -ItemType Directory -Force -Path $TargetImages | Out-Null
New-Item -ItemType Directory -Force -Path $TargetLogs | Out-Null
New-Item -ItemType Directory -Force -Path $TargetVideo | Out-Null

$MainImageExcludeDirs = @("_debug", "Other", "low_score")
$LowScoreExcludeDirs = @("_debug", "Help", "Other")

Invoke-RobocopyWithProgress `
    -Source $SourceOutput `
    -Destination $TargetImages `
    -Activity "複製分類圖片" `
    -ExcludedDirectories $MainImageExcludeDirs

$SourceLowScore = Join-Path $SourceOutput "low_score"
if (Test-Path -LiteralPath $SourceLowScore) {
    Invoke-RobocopyWithProgress `
        -Source $SourceLowScore `
        -Destination (Join-Path $TargetImages "low_score") `
        -Activity "複製 low_score 分類圖片" `
        -ExcludedDirectories $LowScoreExcludeDirs
}

Copy-ReportHtmlWithBundledAssets `
    -Source $SourceOutput `
    -Destination $TargetReport `
    -AssetFolderName "report_assets"

Copy-TopLevelFilesWithProgress `
    -Source $SourceOutput `
    -Destination $TargetReport `
    -Activity "複製報告文字檔案" `
    -Extensions @(".md", ".txt")

Copy-ReportAssetsWithProgress `
    -Source $SourceOutput `
    -Destination $TargetReport

Copy-ReportReferencedAssetsWithProgress `
    -Source $SourceOutput `
    -Destination $TargetReport

Copy-TopLevelFilesWithProgress `
    -Source $SourceOutput `
    -Destination $TargetLogs `
    -Activity "複製紀錄檔案" `
    -Extensions @(".csv", ".json")

$CopiedVideos = Copy-OriginalVideosWithProgress `
    -InputVideoDir $SourceInputVideos `
    -Destination $TargetVideo `
    -VideoId $VideoId `
    -GameName $GameName

$Manifest = [ordered]@{
    archived_at = (Get-Date).ToString("s")
    game_name = $GameName
    video_id = $VideoId
    low_score_included = $true
    main_image_excluded_directories = $MainImageExcludeDirs
    low_score_excluded_directories = $LowScoreExcludeDirs
    source_output = $SourceOutput
    source_input_videos = $SourceInputVideos
    copied_videos = $CopiedVideos
    figma_backup_enabled = $false
    figma_note = "Figma export is intentionally not archived. Future Figma board generation should read from cloud database / hashtag search."
    target_path = $TargetBase
}

$Manifest | ConvertTo-Json -Depth 4 |
    Set-Content -Path (Join-Path $TargetLogs "archive_manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "歸檔完成：" -ForegroundColor Green
Write-Host $TargetBase


