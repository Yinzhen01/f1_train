# F1 Static Stand Warm-Up Workflow

This workflow is for bootstrapping F1 29DOF motion imitation from the first
stable standing frame of:

```text
resources/motions/f1/v1.5/raw/motion_walk_0.6ms.csv
```

## Goal

Do not start full walking imitation directly from a new retargeted motion.
First train a steady standing policy against the first CSV frame, then expand
to short motion clips and finally to the full walk.

## Prepared Static Reference

The first CSV frame is converted to a two-frame static NPZ:

```text
resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0.npz
resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0_bodypos.npz
```

The generated reference repeats frame 0 twice, reads CSV joint columns as
radians, sets all root/DOF velocities to zero, and raises the root by `0.026m`.
This clears the observed first-frame MuJoCo ground penetration while leaving a
small safety gap.

To regenerate:

```bash
python humanoid/scripts/create_static_stand_motion.py \
  --csv resources/motions/f1/v1.5/raw/motion_walk_0.6ms.csv \
  --urdf resources/robots/f1_v1.5/urdf/F1_29DOF_perfect_mirrored.urdf \
  --output resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0.npz \
  --metadata resources/motions/f1/v1.5/metadata_motion_walk_0.6ms_static_stand_frame0.json \
  --frame 0 \
  --height-offset 0.026 \
  --duration 0.02 \
  --joint-unit radians

python humanoid/scripts/augment_motion_body_pos_mujoco.py \
  --input resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0.npz \
  --mjcf resources/robots/f1_v1.5/mjcf/F1_29DOF_flat.xml \
  --output resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0_bodypos.npz
```

## Task

Use the registered task:

```text
f1_dh_static_stand
```

This task uses the static body-position NPZ by default. It keeps motion
playback speed at `0.0`, resets DOFs/root orientation/root velocity to the
static reference, and prioritizes stable spatial keypoint matching.

## Mandatory Small-Batch GUI Check

Before any large headless/static-stand training run, run a small GUI batch first.
The purpose is to verify:

```text
Initial pose matches frame 0.
Feet are not visibly penetrating or bouncing.
Camera view clearly shows the robot and feet.
Termination reason is understandable.
The robot can survive at least the first few seconds in a small batch.
```

Recommended GUI command on a connected Gradmotion desktop:

```bash
TASK=f1_dh_static_stand \
NUM_ENVS=10 \
MAX_ITERATIONS=100000 \
RUN_NAME=f1_static_stand_gui_10env_$(date +%Y%m%d_%H%M%S) \
VIEWER_REL_POS=1.2,-1.3,0.9 \
VIEWER_REL_LOOKAT=0,0,0.55 \
TERMINATION_DIAG_INTERVAL=20 \
BODY_POS_DIAG_INTERVAL=20 \
bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

Only after the GUI check looks healthy should a larger headless training run be
started.

## Headless Training Baseline

After GUI validation:

```bash
TASK=f1_dh_static_stand \
NUM_ENVS=3000 \
MAX_ITERATIONS=1500 \
RUN_NAME=f1_static_stand_3000env_$(date +%Y%m%d_%H%M%S) \
bash ops/gradmotion/gui-desktop-train.sh train
```

Watch `Mean episode length` first. For static standing, it should climb
quickly; if it stays near the early-death range, return to GUI diagnostics
instead of running the full schedule.
