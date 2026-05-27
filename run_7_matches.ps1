param(
    [string]$PythonExe = "E:\miniconda\envs\py310\python.exe",
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$TracknetDevice = "cuda",
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$PoseDevice = "cuda",
    [ValidateSet("weight", "average", "nonoverlap")]
    [string]$TracknetEvalMode = "weight",
    [int]$TracknetBatchSize = 4,
    [double]$TracknetThreshold = 0.20,
    [ValidateSet("reference", "raw_prediction", "filtered_prediction")]
    [string]$TrajectoryMode = "filtered_prediction",
    [int]$PoseImgsz = 960,
    [int]$DetectInterval = 1,
    [switch]$DownloadIfMissing,
    [switch]$SelectCourtEachVideo,
    [switch]$EmbeddedPanels,
    [switch]$CinematicFx,
    [switch]$NoFrontendExport,
    [switch]$ReuseRawPredictions,
    [switch]$Force,
    [string[]]$OnlyVideoIds = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $root "run_pipeline.py"
$selectCourtScript = Join-Path $root "scripts\tools\select_court.py"
$downloadScript = Join-Path $root "scripts\tools\download_7_matches.py"
$inputsDir = Join-Path $root "inputs"
$outputDir = Join-Path $root "output"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing pipeline runner: $runner"
}
if (-not (Test-Path -LiteralPath $selectCourtScript)) {
    throw "Missing court selection script: $selectCourtScript"
}
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$videos = @(
    [pscustomobject]@{ Id = "pro_match17_1_02_02"; InputVideo = (Join-Path $inputsDir "pro_match17_1_02_02.mp4"); CourtPoints = "425,365,884,368,991,675,222,671" },
    [pscustomobject]@{ Id = "pro_match17_1_15_13"; InputVideo = (Join-Path $inputsDir "pro_match17_1_15_13.mp4"); CourtPoints = "425,365,884,368,991,675,222,671" },
    [pscustomobject]@{ Id = "pro_match17_2_01_01"; InputVideo = (Join-Path $inputsDir "pro_match17_2_01_01.mp4"); CourtPoints = "434,352,846,352,992,676,223,669" },
    [pscustomobject]@{ Id = "pro_match17_2_08_05"; InputVideo = (Join-Path $inputsDir "pro_match17_2_08_05.mp4"); CourtPoints = "434,352,846,352,992,676,223,669" },
    [pscustomobject]@{ Id = "pro_match17_2_15_11"; InputVideo = (Join-Path $inputsDir "pro_match17_2_15_11.mp4"); CourtPoints = "434,352,846,352,992,676,223,669" },
    [pscustomobject]@{ Id = "pro_match17_2_18_11"; InputVideo = (Join-Path $inputsDir "pro_match17_2_18_11.mp4"); CourtPoints = "434,352,846,352,992,676,223,669" },
    [pscustomobject]@{ Id = "pro_match19_1_01_01"; InputVideo = (Join-Path $inputsDir "pro_match19_1_01_01.mp4"); CourtPoints = "416,423,864,423,944,706,227,706" }
)

if ($OnlyVideoIds.Count -gt 0) {
    $selected = @($videos | Where-Object { $_.Id -in $OnlyVideoIds })
    if ($selected.Count -ne $OnlyVideoIds.Count) {
        $knownIds = $videos.Id -join ", "
        throw "Unknown video id in -OnlyVideoIds. Known ids: $knownIds"
    }
}
else {
    $selected = $videos
}

function Select-CourtPoints {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VideoPath
    )

    Write-Host "[INFO] Select court points for $VideoPath"
    $output = & $PythonExe $selectCourtScript $VideoPath 2>&1
    $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"
    Write-Host $text
    if ($LASTEXITCODE -ne 0) {
        throw "Court point selection failed for $VideoPath"
    }

    $match = [regex]::Match($text, '--court_points\s+"([^"]+)"')
    if (-not $match.Success) {
        throw "Could not parse court points from selector output for $VideoPath"
    }
    return $match.Groups[1].Value
}

function Test-CompleteBallCsv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$VideoPath,
        [Parameter(Mandatory = $true)]
        [string]$CsvPath
    )

    if (-not (Test-Path -LiteralPath $CsvPath)) {
        return $false
    }

    $checkCode = @'
import csv
import cv2
import sys

video_path = sys.argv[1]
csv_path = sys.argv[2]

cap = cv2.VideoCapture(video_path)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()

with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
frames = [int(float(row["Frame"])) for row in rows]
valid = len(frames) == frame_count and len(set(frames)) == frame_count and sorted(frames) == list(range(frame_count))

print("OK" if valid else f"BAD:{len(frames)}:{frame_count}")
'@

    $result = & $PythonExe -c $checkCode $VideoPath $CsvPath
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    return (($result | Select-Object -Last 1) -eq "OK")
}

function Invoke-Pipeline {
    param(
        [Parameter(Mandatory = $true)]
        $Video,
        [Parameter(Mandatory = $true)]
        [string]$CourtPoints,
        [Parameter(Mandatory = $true)]
        [bool]$DoFrontendExport
    )

    $workRoot = Join-Path $outputDir $Video.Id
    $rawBallCsv = Join-Path $workRoot "tracknet_v3_result_regen\$($Video.Id)_ball.csv"
    $referenceBallCsv = Join-Path $inputsDir "$($Video.Id)_ball.csv"

    $args = @(
        $runner,
        "--input-video", $Video.InputVideo,
        "--court-points", $CourtPoints,
        "--tracknet-device", $TracknetDevice,
        "--tracknet-batch-size", "$TracknetBatchSize",
        "--pose-device", $PoseDevice,
        "--tracknet-threshold", "$TracknetThreshold",
        "--tracknet-eval-mode", $TracknetEvalMode,
        "--trajectory-mode", $TrajectoryMode,
        "--reference-ball-csv", $referenceBallCsv,
        "--pose-imgsz", "$PoseImgsz",
        "--detect-interval", "$DetectInterval"
    )

    if ($ReuseRawPredictions -and (Test-CompleteBallCsv -VideoPath $Video.InputVideo -CsvPath $rawBallCsv)) {
        Write-Host "[INFO] Reusing structurally complete raw prediction for $($Video.Id): $rawBallCsv"
        $args += @("--ball-csv", $rawBallCsv)
    }

    if ($EmbeddedPanels) {
        $args += "--embedded-panels"
    }
    if ($CinematicFx) {
        $args += "--cinematic-fx"
    }
    if (-not $DoFrontendExport) {
        $args += "--no-frontend-export"
    }

    Write-Host "[INFO] Running pipeline for $($Video.Id)"
    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "Pipeline failed for $($Video.Id) with exit code $LASTEXITCODE"
    }
}

$missingVideos = @($selected | Where-Object { -not (Test-Path -LiteralPath $_.InputVideo) })
if ($missingVideos.Count -gt 0) {
    if (-not $DownloadIfMissing) {
        $missingList = $missingVideos.Id -join ", "
        throw "Missing input videos: $missingList. Re-run with -DownloadIfMissing to fetch them first."
    }

    Write-Host "[INFO] Downloading missing professional match videos..."
    & $PythonExe $downloadScript
    if ($LASTEXITCODE -ne 0) {
        throw "Download script failed with exit code $LASTEXITCODE"
    }
}

$pending = @()
foreach ($video in $selected) {
    $finalVideo = Join-Path (Join-Path $outputDir $video.Id) "$($video.Id)_final.mp4"
    if ((Test-Path -LiteralPath $finalVideo) -and (-not $Force)) {
        Write-Host "[SKIP] Final output already exists for $($video.Id): $finalVideo"
        continue
    }
    $pending += $video
}

if ($pending.Count -eq 0) {
    Write-Host "[DONE] Nothing to run. All selected videos already have final outputs."
    return
}

for ($i = 0; $i -lt $pending.Count; $i++) {
    $video = $pending[$i]
    $doFrontendExport = (-not $NoFrontendExport) -and ($i -eq ($pending.Count - 1))

    $courtPoints = $video.CourtPoints
    if ($SelectCourtEachVideo -or [string]::IsNullOrWhiteSpace($courtPoints)) {
        $courtPoints = Select-CourtPoints -VideoPath $video.InputVideo
    }
    else {
        Write-Host "[INFO] Using preset court points for $($video.Id): $courtPoints"
    }

    Invoke-Pipeline -Video $video -CourtPoints $courtPoints -DoFrontendExport:$doFrontendExport
}

Write-Host "[DONE] Batch run finished."
