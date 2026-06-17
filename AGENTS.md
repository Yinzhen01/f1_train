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
doc/gm_multi_account_workflow.md
```

Gradmotion multi-account application, gm-cli profile setup, local-only account ledger, quota estimation from initial credit/unit price/runtime, pre-submission account checks, task naming, and failure handling.

```text
doc/f1_remote_training_deployment.md
```

Remote training deployment and environment notes for F1 training, including local/remote setup, smoke tests, viewer/headless usage, monitoring, and deployment helper script context.

```text
doc/gradmotion_reverse_ssh_gui_workflow.md
```

Gradmotion reverse SSH workflow for letting Codex operate a GUI cloud desktop through a public jump host while keeping windows visible on the user's active desktop session, including DISPLAY/XAUTHORITY handling and cleanup rules.

```text
doc/gradmotion_codex_gui_minimal_repro.md
```

Minimal reproduction checklist for reconnecting Codex to a new Gradmotion GUI cloud desktop through reverse SSH, validating visible GUI windows, running viewer smoke tests, and cleaning up temporary access.

```text
doc/project_structure_and_cleanup.md
```

Project structure and cleanup guide, including root directory policy, gm-cli payload placement, cleanup workflow, and current housekeeping decisions.

```text
doc/cloud_task_artifact_layout.md
```

Local-only cloud task artifact layout, including downloaded logs, checkpoints, task metadata, model-list records, TensorBoard files, and checksum conventions.

```text
to_infer/f1_checkpoint_inference_handoff.md
```

Inference-facing F1 checkpoint handoff notes, including the deployment input shape, observation layout, joint/action order, action post-processing, default pose, PD gains, history buffer behavior, and task/checkpoint selection caveats.

```text
doc/resource_layout.md
```

URDF model and retargeted motion directory layout, variant naming (perfect/physically mirrored), currently active F1 model, and related code entry points.

## Key Resource Pointers

Currently active model for F1 training:

```text
resources/robots/f1_v1.5/urdf/F1_29DOF_physically_mirrored.urdf
```

This matches `humanoid/envs/f1/f1_dh_stand_config.py` and the default F1 motion metadata. Treat `F1_29DOF_perfect_mirrored.urdf` as an alternate URDF variant unless the training config is explicitly changed.

For the full URDF and retargeted motion directory layout, variant naming, and related code entry points, use:

```text
doc/resource_layout.md
```

## Gradmotion GUI Desktop Entry Point

When the user asks how to use a new Gradmotion GUI cloud desktop for training, start from:

```bash
bash ops/gradmotion/bootstrap-gui-desktop.sh
```

This one-shot bootstrap runs `git pull`, installs the checkout into the active Python environment, checks GPU/DISPLAY/Isaac Gym/PyTorch/F1 task shape, then runs `gui-single` and `gui-smoke` viewer smoke tests. It does not start formal long training unless the user explicitly asks for it or passes `--train`.

For the detailed manual and scripted GUI workflow, use:

```text
doc/f1_remote_training_deployment.md
```

When Codex needs to operate the Gradmotion GUI desktop remotely while the user watches the interface, use:

```text
doc/gradmotion_codex_gui_minimal_repro.md
doc/gradmotion_reverse_ssh_gui_workflow.md
```

For a fresh Gradmotion GUI desktop that has already cloned this repository, the preferred one-shot entry point is:

```bash
bash ops/gradmotion/start-codex-tunnel.sh
```

When the goal is F1 29DOF retargeted motion imitation in the Gradmotion GUI desktop, prefer the motion-imitation task and focused viewer entry point:

```bash
TASK=f1_dh_motion_imitation NUM_ENVS=10 MAX_ITERATIONS=100000 \
  RUN_NAME=f1_motion_imitation_gui_10env_YYYYMMDD \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

This is preferred over `f1_dh_stand` for motion imitation because `f1_dh_motion_imitation` enables reference actions, root orientation/velocity reset, and nonzero motion root/velocity/orientation reward scales. Use `doc/gradmotion_codex_gui_minimal_repro.md` and `doc/gradmotion_reverse_ssh_gui_workflow.md` for detailed checks, including world-space keypoint reward, keypoint reset thresholds, and the current 3000-env Gradmotion training baseline.

If the retargeted motion starts in a dynamic single-support phase and the robot consistently falls sideways within the first few tenths of a second, generate a rephased motion that starts from a more stable double-support frame before training:

```bash
python humanoid/scripts/rephase_motion_npz.py --input INPUT.npz --output OUTPUT.npz --add-foot-contacts
```

Then pass the generated NPZ through `MOTION_REFERENCE_FILE=...` and consider enabling `MOTION_CONTACT_SCHEDULE_SCALE` plus stronger early root/keypoint reward scale overrides in `humanoid/scripts/train_focused_view.py`.

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

Git commit and push rules:

1. Use Chinese commit messages for future commits.
2. Before committing, analyze whether the pending changes belong in one commit or multiple commits. Use one commit only when the changes share a single meaningful topic; split unrelated or independently reviewable changes into separate commits.
3. Review `git status` and staged diffs before committing to avoid mixing unrelated files.
4. Do not commit local-only files, temporary payloads, cloud artifacts, logs, checkpoints, exported models, credentials, tokens, passwords, signed URLs, or recharge records.
5. A commit does not imply a push. Push only when the user explicitly asks for it, and check branch/remote/worktree state first.

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
