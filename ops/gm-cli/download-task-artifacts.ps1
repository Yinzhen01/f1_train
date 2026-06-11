param(
    [Parameter(Mandatory = $true)]
    [string]$TaskId,
    [string]$ArtifactRoot,
    [string]$InferTrainingRoot = "F:\Projects\agibot_x1_infer\training",
    [string]$SyncToInfer = "true",
    [string]$GmCli = "C:\Users\HP\AppData\Roaming\npm\gm.cmd"
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ArtifactRoot)) {
    $ArtifactRoot = Join-Path $scriptRoot "..\..\cloud_artifacts\tasks"
}

$syncToInferValue = switch -Regex ($SyncToInfer.Trim()) {
    "^(1|true|yes)$" { $true; break }
    "^(0|false|no)$" { $false; break }
    default { throw "SyncToInfer must be true/false, yes/no, or 1/0. Got: $SyncToInfer" }
}

if (-not (Test-Path -LiteralPath $GmCli -PathType Leaf)) {
    throw "gm-cli entry point not found: $GmCli"
}

$taskRoot = Join-Path $ArtifactRoot $TaskId
$metadataDir = Join-Path $taskRoot "metadata"
$logsDir = Join-Path $taskRoot "logs"
$checkpointDir = Join-Path $taskRoot "checkpoints"
New-Item -ItemType Directory -Force -Path $metadataDir, $logsDir, $checkpointDir | Out-Null

$taskInfoPath = Join-Path $metadataDir "task-info.json"
$modelListPath = Join-Path $metadataDir "model-list.json"
$logPath = Join-Path $logsDir "main.log"

$infoText = & $GmCli task info --task-id $TaskId
$infoText | Set-Content -Encoding UTF8 -Path $taskInfoPath
$info = $infoText | ConvertFrom-Json

if ($info.data.argoLogDownloadUrl) {
    Invoke-WebRequest -Uri $info.data.argoLogDownloadUrl -OutFile $logPath
} else {
    $logText = & $GmCli task logs --task-id $TaskId --raw --no-request-log
    $logText | Set-Content -Encoding UTF8 -Path $logPath
}

$modelText = & $GmCli task model list --task-id $TaskId
$modelText | Set-Content -Encoding UTF8 -Path $modelListPath
$models = ($modelText | ConvertFrom-Json).data.rows

foreach ($model in $models) {
    if (-not $model.policUrlDown) {
        continue
    }
    $outputPath = Join-Path $checkpointDir $model.fileName
    Invoke-WebRequest -Uri $model.policUrlDown -OutFile $outputPath
}

$checksumPath = Join-Path $taskRoot "checksums.sha256"
$checkpointFiles = Get-ChildItem -LiteralPath $checkpointDir -Filter "model_*.pt" -File -ErrorAction SilentlyContinue
$checksumLines = foreach ($file in $checkpointFiles) {
    $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
    $relativePath = "checkpoints/$($file.Name)"
    "$($hash.Hash)  $relativePath"
}
$checksumLines | Set-Content -Encoding ASCII -Path $checksumPath

$syncResult = $null
if ($syncToInferValue) {
    $syncResult = & (Join-Path $scriptRoot "sync-task-artifacts.ps1") `
        -TaskId $TaskId `
        -SourceRoot $ArtifactRoot `
        -DestinationRoot $InferTrainingRoot
}

[PSCustomObject]@{
    TaskId = $TaskId
    ArtifactDirectory = (Resolve-Path -LiteralPath $taskRoot).Path
    SyncedToInfer = $syncToInferValue
    InferTrainingDirectory = if ($syncResult) { $syncResult.Destination } elseif ($syncToInferValue) { Join-Path $InferTrainingRoot $TaskId } else { $null }
}
