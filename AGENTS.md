# AGENTS.md

This is the default project handoff file for Codex agents working in this repository. Keep this file concise: it should route agents to the right detailed documents instead of duplicating full procedures.

## Project Context

Repository root:

```text
E:\Projects\agibot_x1_train
```

Current GitHub repository:

```text
https://github.com/Yinzhen01/f1_train.git
branch: main
```

This project contains F1 29DOF Isaac Gym training code based on the Agibot X1 training repository.

## Document Registry

Use these documents for detailed workflows:

```text
doc/gm_cli_task_submission_workflow.md
```

Detailed gm-cli cloud task submission workflow, including resource/image/project lookup, create JSON templates, dry-run/create/run/log commands, successful task records, private GitHub troubleshooting, and formal training recommendations.

```text
doc/f1_remote_training_deployment.md
```

Remote training deployment and environment notes for F1 training, including local/remote setup, smoke tests, viewer/headless usage, monitoring, and deployment helper script context.

```text
doc/project_structure_and_cleanup.md
```

Project structure and cleanup guide, including root directory policy, gm-cli payload placement, cleanup workflow, and current housekeeping decisions.

```text
doc/cloud_task_artifact_layout.md
```

Local-only cloud task artifact layout, including downloaded logs, checkpoints, task metadata, model-list records, TensorBoard files, and checksum conventions.

## AGENTS.md Registration Policy

Register content here only when a future agent should know it before acting in this repository.

Add entries for:

```text
Stable workflow entry points that route to detailed docs.
Safety, cost, data-integrity, or cloud-operation rules.
Tool entry points and machine-specific caveats that prevent wrong commands.
Long-lived directory conventions and artifact ownership boundaries.
Known-good baselines that future debugging should compare against.
External service caveats that affect task success or reproducibility.
```

Do not add:

```text
Full procedures that belong in doc/.
Temporary task payloads, raw logs, signed URLs, or downloaded artifacts.
One-off experiment notes unless they become a durable baseline.
Detailed implementation notes that are discoverable from code.
Large file lists, transient TODOs, or personal scratch notes.
```

Keep this file concise: register the existence, location, and reason for each durable rule or document; put the details in `doc/` or `ops/`.

## Operating Rules

Before creating, editing, running, stopping, or deleting cloud tasks:

1. Read `doc/gm_cli_task_submission_workflow.md`.
2. Audit current local Git state and existing local `create-*.json` payloads.
3. Audit relevant cloud task state if a task ID is known.
4. Report completed items, missing/uncertain items, and recommended next action.
5. Wait for user confirmation before starting long-running or cost-incurring training.

Do not commit temporary gm-cli payloads:

```text
create-*.json
edit-*.json
copy-*.json
```

They are request payloads and should stay local under:

```text
ops/gm-cli/payloads/
```

Do not commit downloaded cloud task artifacts:

```text
cloud_artifacts/
```

Downloaded logs, checkpoints, model-list records, and task metadata should follow:

```text
doc/cloud_task_artifact_layout.md
```

After downloading a completed Gradmotion task directory under `cloud_artifacts/tasks/<TASK_ID>/`, sync it to the inference repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\sync-task-artifacts.ps1 -TaskId TASK_xxx
```

The expected inference-side destination is:

```text
F:\Projects\agibot_x1_infer\training\<TASK_ID>\
```

Writing to the inference repository training directory may require an elevated shell.

For new completed tasks, prefer the downloader helper because it downloads and syncs in one step:

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\download-task-artifacts.ps1 -TaskId TASK_xxx
```

## gm-cli Entry Point

On this Windows machine, do not call `gm` directly from PowerShell because it may resolve to `Get-Member`.

Use:

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" <args>
```

For all gm-cli details, commands, known-good payloads, and troubleshooting, use:

```text
doc/gm_cli_task_submission_workflow.md
```

## Known Good Cloud Baseline

The known successful smoke test is recorded in detail in `doc/gm_cli_task_submission_workflow.md`.

Summary:

```text
taskId: TASK_20260608_073
status: Completed
resource: ESKU000004 / 1*A10*24G
image: BJX00000001 / V000124 / Isaac GYM:preview-4
commitId: 64e0501f72dc8759481c487e50a3ea2c5d564aa2
startScript: gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_stand --headless --num_envs=16 --max_iterations=5
```

This verifies that public GitHub pull, Isaac Gym startup, F1 29DOF registration, short training, and checkpoint upload work.

## Private Repository Caveat

Public GitHub repository mode has been verified. Private repository mode previously failed to populate `taskCodeInfo.commitId`.

If the repository is private, validate Gradmotion Git settings before running training:

```text
GitHub account name: Yinzhen01
GitHub token: has code/contents read permission for Yinzhen01/f1_train
```

A private-repo cloud task is only considered fixed when `taskCodeInfo.commitId` is non-empty and logs show `/workspace/f1_train/` without `can't open file`.
