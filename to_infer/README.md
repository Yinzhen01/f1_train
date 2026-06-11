# To Infer Handoff

This directory contains inference-facing handoff materials that can be shared with the F1 inference repository or deployment team.

Current contents:

```text
f1_checkpoint_inference_handoff.md
```

Use this document for the `TASK_20260611_032` checkpoint questions: commit ID, export shape, observation layout, joint/action order, action post-processing, default pose, PD gains, and history-buffer rules.

Training artifacts and checkpoints are not committed here. Downloaded task outputs should stay under `cloud_artifacts/tasks/<TASK_ID>/` locally and are synced to:

```text
F:\Projects\agibot_x1_infer\training\<TASK_ID>\
```
