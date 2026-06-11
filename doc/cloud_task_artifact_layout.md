# Cloud Task Artifact Layout

This document defines the local directory convention for files downloaded from Gradmotion cloud tasks.

## Purpose

Cloud training can produce many local files: logs, checkpoint models, task metadata, TensorBoard events, and checksum records. These files are useful for debugging and reproducibility, but they can be large and environment-specific.

Keep them organized under a local-only directory and out of Git.

## Root Directory

Downloaded cloud artifacts belong under:

```text
cloud_artifacts/tasks/<TASK_ID>/
```

`cloud_artifacts/` is ignored by Git.

Do not store downloaded checkpoints, task logs, or signed URLs in `doc/`, `ops/`, `resources/`, or the repository root.

## Per-Task Layout

Use this layout for each task:

```text
cloud_artifacts/
  tasks/
    TASK_YYYYMMDD_NNN/
      metadata/
        task-info.json
        model-list.json
      logs/
        train.log
      checkpoints/
        model_0.pt
        model_*.pt
      tensorboard/
      checksums.sha256
```

## File Roles

```text
metadata/task-info.json
```

Raw `gm task info` output. Preserve this when possible because it records task status, start script, image, resource, commit ID, runtime, and cloud metadata.

```text
metadata/model-list.json
```

Raw `gm task model list` output. Preserve this when downloading checkpoints because it traces each `.pt` file back to the cloud model record and storage path.

```text
logs/train.log
```

Raw task log downloaded from `gm task logs`.

```text
checkpoints/model_*.pt
```

Downloaded PyTorch checkpoint files. These are large local artifacts and must not be committed.

```text
tensorboard/
```

TensorBoard event files if they are downloaded later.

```text
checksums.sha256
```

SHA256 checksums for downloaded checkpoint files, using paths relative to the task directory.

Example:

```text
5BF2375CD7B7274628117A9801EDCF984C9F7343EAA40D7708B54B8A299443E2  checkpoints/model_0.pt
```

## gm-cli Download Pattern

Use the Windows gm-cli entry point:

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" <args>
```

Recommended retrieval sequence:

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task info --task-id TASK_xxx
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task logs --task-id TASK_xxx --raw --no-request-log
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task model list --task-id TASK_xxx --limit 20
```

Download checkpoint files from the `policUrlDown` values in `model-list.json`. These are signed URLs and may expire, so keep `model-list.json` as a historical record but refresh it if a download URL stops working.

## Git Policy

Never commit:

```text
cloud_artifacts/
*.pt
*.pth
*.ckpt
full raw training logs
signed download URLs intended only for local use
```

Short human-readable conclusions may be added to `doc/` when they are useful for future work, but large raw artifacts should stay local.

## Related Directories

gm-cli request payloads are not cloud artifacts. Keep them under:

```text
ops/gm-cli/payloads/
```

Payload files such as `create-*.json`, `edit-*.json`, and `copy-*.json` should remain uncommitted unless a specific known-good template is intentionally preserved.

