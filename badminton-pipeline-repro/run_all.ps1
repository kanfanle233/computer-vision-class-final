param(
    [Parameter(Mandatory = $true)]
    [string]$InputVideo,
    [string]$WorkRoot = "",
    [string]$CourtPoints = "",
    [string]$BallCsv = "",
    [double]$CourtWidthM = 6.1,
    [double]$CourtLengthM = 13.4,
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$TracknetDevice = "auto",
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$PoseDevice = "auto",
    [double]$TracknetThreshold = 0.15,
    [ValidateSet("weight", "average", "nonoverlap")]
    [string]$TracknetEvalMode = "weight",
    [int]$PoseImgsz = 960,
    [int]$DetectInterval = 1,
    [double]$BallTopPadPx = 160.0,
    [double]$BallSidePadPx = 80.0,
    [double]$BallMinMotionScore = 4.0,
    [int]$BallMaxInterpGap = 2,
    [string]$PythonExe = "python",
    [switch]$ManualCourt,
    [switch]$FilterBall,
    [switch]$DrawCourtPolygon,
    [switch]$EmbeddedPanels,
    [switch]$CinematicFx,
    [switch]$NoFrontendExport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $root "run_pipeline.py"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Missing portable pipeline launcher: $runner"
}

$pipelineArgs = @(
    $runner,
    "--input-video", $InputVideo,
    "--tracknet-device", $TracknetDevice,
    "--pose-device", $PoseDevice,
    "--tracknet-threshold", "$TracknetThreshold",
    "--tracknet-eval-mode", $TracknetEvalMode,
    "--pose-imgsz", "$PoseImgsz",
    "--detect-interval", "$DetectInterval",
    "--court-width-m", "$CourtWidthM",
    "--court-length-m", "$CourtLengthM",
    "--ball-top-pad-px", "$BallTopPadPx",
    "--ball-side-pad-px", "$BallSidePadPx",
    "--ball-min-motion-score", "$BallMinMotionScore",
    "--ball-max-interp-gap", "$BallMaxInterpGap"
)

if ($WorkRoot) {
    $pipelineArgs += @("--work-root", $WorkRoot)
}
if ($CourtPoints) {
    $pipelineArgs += @("--court-points", $CourtPoints)
}
if ($BallCsv) {
    $pipelineArgs += @("--ball-csv", $BallCsv)
}
if ($ManualCourt) {
    $pipelineArgs += "--manual-court"
}
if ($FilterBall) {
    $pipelineArgs += "--filter-ball"
}
if ($DrawCourtPolygon) {
    $pipelineArgs += "--draw-court-polygon"
}
if ($EmbeddedPanels) {
    $pipelineArgs += "--embedded-panels"
}
if ($CinematicFx) {
    $pipelineArgs += "--cinematic-fx"
}
if ($NoFrontendExport) {
    $pipelineArgs += "--no-frontend-export"
}

Write-Host "[INFO] Starting cross-platform pipeline via $PythonExe"
& $PythonExe @pipelineArgs
if ($LASTEXITCODE -ne 0) {
    throw "Pipeline failed with exit code $LASTEXITCODE."
}
