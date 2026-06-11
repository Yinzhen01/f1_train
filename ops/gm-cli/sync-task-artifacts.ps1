param(
    [string[]]$TaskId,
    [string]$SourceRoot,
    [string]$DestinationRoot = "F:\Projects\agibot_x1_infer\training"
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = Join-Path $scriptRoot "..\..\cloud_artifacts\tasks"
}

$sourceRootPath = (Resolve-Path -LiteralPath $SourceRoot).Path
New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null
$destinationRootPath = (Resolve-Path -LiteralPath $DestinationRoot).Path

if ($TaskId -and $TaskId.Count -gt 0) {
    $tasks = foreach ($id in $TaskId) {
        $path = Join-Path $sourceRootPath $id
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            throw "Task artifact directory not found: $path"
        }
        Get-Item -LiteralPath $path
    }
} else {
    $tasks = Get-ChildItem -LiteralPath $sourceRootPath -Directory
}

foreach ($task in $tasks) {
    $destination = Join-Path $destinationRootPath $task.Name
    New-Item -ItemType Directory -Force -Path $destination | Out-Null

    Get-ChildItem -LiteralPath $task.FullName -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }

    [PSCustomObject]@{
        TaskId = $task.Name
        Source = $task.FullName
        Destination = $destination
    }
}
