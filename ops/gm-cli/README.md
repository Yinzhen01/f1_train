# gm-cli Operations

This directory keeps gm-cli operational files out of the repository root.

Detailed workflow:

```text
../../doc/gm_cli_task_submission_workflow.md
```

Project structure policy:

```text
../../doc/project_structure_and_cleanup.md
```

Cloud artifact layout:

```text
../../doc/cloud_task_artifact_layout.md
```

## Payloads

Use this directory for local request payloads:

```text
ops/gm-cli/payloads/
```

Payloads such as `create-*.json`, `edit-*.json`, and `copy-*.json` are local operational files and should not be committed.

Known-good local payload:

```text
payloads/create-validate-a10-public-known-good.json
```

This payload corresponds to the successful smoke task:

```text
TASK_20260608_073
```

## Downloaded Task Artifacts

Keep downloaded cloud outputs outside `ops/`:

```text
cloud_artifacts/tasks/<TASK_ID>/
```

Expected per-task layout:

```text
metadata/task-info.json
metadata/model-list.json
logs/train.log
checkpoints/model_*.pt
tensorboard/
checksums.sha256
```

`cloud_artifacts/` is local-only and ignored by Git.

See `../../doc/cloud_task_artifact_layout.md` for file roles, metadata conventions, and checkpoint checksum policy.

## Inference Repository Sync

After a Gradmotion task completes, download and sync artifacts with:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\download-task-artifacts.ps1 -TaskId TASK_xxx
```

This copies the downloaded task directory to:

```text
F:\Projects\agibot_x1_infer\training\<TASK_ID>\
```

Writing to that destination may require an elevated shell.

For task directories that are already present under `cloud_artifacts/tasks/`, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\sync-task-artifacts.ps1 -TaskId TASK_xxx
```
