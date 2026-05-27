param(
    [Parameter(Mandatory = $true)]
    [string]$InputVideo,
    [string]$WorkRoot = "",
    [string]$CourtPoints = "",
    [string]$BallCsv = "",
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$TracknetDevice = "auto",
    [ValidateSet("auto", "cuda", "mps", "cpu")]
    [string]$PoseDevice = "auto",
    [double]$TracknetThreshold = 0.15,
    [ValidateSet("weight", "average", "nonoverlap")]
    [string]$TracknetEvalMode = "weight",
    [int]$TracknetBatchSize = 4,
    [int]$PoseImgsz = 960,
    [int]$DetectInterval = 1,
    [string]$PythonExe = "python",
    [switch]$ManualCourt,
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
    "--tracknet-batch-size", "$TracknetBatchSize",
    "--pose-imgsz", "$PoseImgsz",
    "--detect-interval", "$DetectInterval"
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
