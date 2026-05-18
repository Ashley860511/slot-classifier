<#
.SYNOPSIS
  Archive slot classifier outputs to the company AI survey fileserver.

.DESCRIPTION
  Copies one video's classifier output, reports, logs, and Figma export package
  into the company network drive using Robocopy.

.EXAMPLE
  .\archive_to_fileserver.ps1 -VideoId "10" -GameName "Goal Rush"

.EXAMPLE
  .\archive_to_fileserver.ps1 -VideoId "WildCoaster" -GameName "WildCoaster" -IncludeLowScore
#>
param(
    [Parameter(Mandatory=$true)]
    [string]$VideoId,

    [Parameter(Mandatory=$true)]
    [string]$GameName,

    [switch]$IncludeLowScore,

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
        [Parameter(Mandatory=$true)] [string[]]$ExcludedDirectories
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
$TargetFigma = Join-Path $TargetBase "03_figma"
$TargetLogs = Join-Path $TargetBase "04_logs"

$SourceOutput = Join-Path $Root "project\output\$VideoId"
$SourceFigma = Join-Path $Root "figma_export"

if (-not (Test-Path -LiteralPath $SourceOutput)) {
    throw "找不到分類輸出資料夾：$SourceOutput"
}

if (-not (Test-Path -LiteralPath $TargetRoot)) {
    throw "找不到公司網路磁碟路徑，請確認 VPN / 網路磁碟權限：$TargetRoot"
}

New-Item -ItemType Directory -Force -Path $TargetReport | Out-Null
New-Item -ItemType Directory -Force -Path $TargetImages | Out-Null
New-Item -ItemType Directory -Force -Path $TargetFigma | Out-Null
New-Item -ItemType Directory -Force -Path $TargetLogs | Out-Null

$ExcludeDirs = @("_debug", "Other")
if (-not $IncludeLowScore) {
    $ExcludeDirs += "low_score"
}

Invoke-RobocopyWithProgress `
    -Source $SourceOutput `
    -Destination $TargetImages `
    -Activity "複製分類圖片" `
    -ExcludedDirectories $ExcludeDirs

Copy-TopLevelFilesWithProgress `
    -Source $SourceOutput `
    -Destination $TargetReport `
    -Activity "複製報告檔案" `
    -Extensions @(".html", ".md", ".txt")

Copy-ReportAssetsWithProgress `
    -Source $SourceOutput `
    -Destination $TargetReport

Copy-TopLevelFilesWithProgress `
    -Source $SourceOutput `
    -Destination $TargetLogs `
    -Activity "複製紀錄檔案" `
    -Extensions @(".csv", ".json")

if (Test-Path -LiteralPath $SourceFigma) {
    Invoke-RobocopyWithProgress `
        -Source $SourceFigma `
        -Destination $TargetFigma `
        -Activity "複製 Figma 匯出" `
        -ExcludedDirectories @()
}

$Manifest = [ordered]@{
    archived_at = (Get-Date).ToString("s")
    game_name = $GameName
    video_id = $VideoId
    include_low_score = [bool]$IncludeLowScore
    excluded_directories = $ExcludeDirs
    source_output = $SourceOutput
    source_figma = $SourceFigma
    target_path = $TargetBase
}

$Manifest | ConvertTo-Json -Depth 4 |
    Set-Content -Path (Join-Path $TargetLogs "archive_manifest.json") -Encoding UTF8

Write-Host ""
Write-Host "歸檔完成：" -ForegroundColor Green
Write-Host $TargetBase

