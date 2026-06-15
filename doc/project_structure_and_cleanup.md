# Project Structure and Cleanup Guide

This document defines how to keep this repository tidy as cloud training, gm-cli payloads, deployment scripts, and experiment records accumulate.

## 1. Purpose

The root directory should stay small and predictable. Detailed workflows belong in `doc/`; operational assets belong in `ops/`; temporary request payloads should not be committed.

This guide should be updated whenever the project structure changes in a way future Codex conversations need to understand.

## 2. Root Directory Policy

Keep only long-lived entry points and core project files in the repository root:

```text
AGENTS.md
CLAUDE.md
README.md
README.zh_CN.md
setup.py
doc/
humanoid/
resources/
ops/
to_infer/
```

Avoid keeping temporary experiment files, generated payloads, copied logs, or one-off artifacts in the root directory.

## 3. Directory Roles

```text
doc/
```

Human-readable project documentation, workflow records, troubleshooting notes, and handoff guides.

Large README media should live under `doc/assets/` for future additions or reorganizations. Existing root-level `doc/*.gif` and `doc/*.jpg` files may remain until a dedicated link-preserving media cleanup is performed.

```text
ops/
```

Operational support files for cloud training, gm-cli usage, deployment, and environment management.

```text
to_infer/
```

Inference-facing handoff materials that can be shared with the F1 inference repository or deployment team. Keep this directory limited to stable docs, manifests, and small config references. Do not commit raw checkpoints, cloud logs, signed URLs, or generated model exports here.

```text
ops/gm-cli/
```

gm-cli-specific operational notes and local payload organization.

```text
ops/gradmotion/
```

Gradmotion desktop, remote deployment, and interactive training helper scripts.

```text
cloud_artifacts/
```

Local-only downloads from cloud tasks, including logs, checkpoint files, task metadata, TensorBoard files, and checksum records. This directory is ignored by Git and should not be committed. Detailed layout is defined in `doc/cloud_task_artifact_layout.md`.

```text
ops/gm-cli/payloads/
```

Local gm-cli request payloads such as `create-*.json`, `edit-*.json`, and `copy-*.json`. These are ignored by Git and should not be committed.

```text
humanoid/
resources/
```

Training code, robot assets, URDFs, meshes, and runtime project content.

## 4. gm-cli Payload Policy

All future gm-cli payloads should be created under:

```text
ops/gm-cli/payloads/
```

Examples:

```text
ops/gm-cli/payloads/create-train-a10.json
ops/gm-cli/payloads/create-smoke-a10.json
ops/gm-cli/payloads/edit-task-note.json
```

Rules:

```text
Do not keep payloads in the repository root.
Do not commit payloads containing task IDs, project IDs, resource IDs, private URLs, or environment-specific choices.
Preserve only known-good local payloads that are useful for reruns.
Delete failed path-experiment payloads after their conclusions are recorded in documentation.
```

The known-good payload currently preserved locally is:

```text
ops/gm-cli/payloads/create-validate-a10-public-known-good.json
```

It corresponds to the successful smoke task:

```text
TASK_20260608_073
```

## 5. Cloud Artifact Policy

Downloaded cloud task outputs should stay under:

```text
cloud_artifacts/tasks/<TASK_ID>/
```

Detailed layout, file roles, and retrieval conventions are defined in:

```text
doc/cloud_task_artifact_layout.md
```

## 6. Cleanup Workflow

Before cleanup:

```powershell
git status --short --branch
Get-ChildItem -Path . -Filter "create-*.json"
Get-ChildItem -Path ops\gm-cli\payloads -Filter "*.json" -ErrorAction SilentlyContinue
```

Cleanup steps:

```text
1. Identify root-level temporary files.
2. Preserve only known-good payloads under ops/gm-cli/payloads/.
3. Delete failed or obsolete local payloads.
4. Update documentation with any lessons learned.
5. Re-run git status and report remaining untracked files.
```

Do not delete unrelated untracked files or directories without explicit user confirmation.

## 7. Current Cleanup Decisions

Applied decisions:

```text
Failed path trial payloads: delete.
Successful create-validate-a10-public.json: preserve as create-validate-a10-public-known-good.json under ops/gm-cli/payloads/.
Future formal training payloads: create under ops/gm-cli/payloads/ and keep uncommitted.
Future downloaded cloud artifacts: create under cloud_artifacts/tasks/<TASK_ID>/ and keep uncommitted.
Default project entry point: AGENTS.md.
Legacy codex.md: delete after AGENTS.md contains the routing rules.
```

Root-level payloads removed during this cleanup:

```text
create-train.json
create-validate.json
create-validate-a10.json
create-validate-a10-rootpath.json
create-validate-a10-workdir.json
create-validate-a10-versionfields.json
create-validate-a10-tokenfix.json
create-validate-a10-public.json
```

## 8. Changelog

```text
2026-06-11
- Added `to_infer/` for inference-facing checkpoint handoff materials.
- Added doc/cloud_task_artifact_layout.md for downloaded cloud task artifact conventions.
- Registered the cloud artifact layout in AGENTS.md.

2026-06-10
- Added this project structure and cleanup guide.
- Registered this guide in AGENTS.md.
- Moved the known-good public A10 smoke payload under ops/gm-cli/payloads/.
- Removed root-level historical gm-cli payloads.
- Removed legacy codex.md in favor of AGENTS.md.
```
