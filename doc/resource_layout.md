# Resource Layout: URDF Models and Retargeted Motions

This document describes the layout of robot models and retargeted reference motion data under `resources/`.

## Robot Models (URDF)

```text
resources/robots/
├── f1_v1.5/urdf/
│   ├── F1_29DOF_perfect_mirrored.urdf
│   ├── F1_29DOF_physically_mirrored.urdf
│   ├── X1_12DOF_perfect_mirrored.urdf
│   ├── X1_12DOF_physically_mirrored.urdf
│   ├── X1_29DOF_perfect_mirrored.urdf
│   └── X1_29DOF_physically_mirrored.urdf
├── Models/urdf/
│   ├── F1_29DOF_physically_mirrored.urdf
│   ├── X1_12DOF_physically_mirrored.urdf
│   └── X1_29DOF_physically_mirrored.urdf
└── x1/urdf/
    └── x1.urdf                              <- original Agibot X1 model
```

Variant naming:

- `perfect_mirrored`: left/right limbs are exact mirrors (idealized symmetry).
- `physically_mirrored`: mirrored from measured physical parameters.

The currently active model for F1 training is:

```text
resources/robots/f1_v1.5/urdf/F1_29DOF_perfect_mirrored.urdf
```

This is the asset path configured by `humanoid/envs/f1/f1_dh_stand_config.py`, and it matches the MuJoCo model used to validate `resources/motions/f1/v1.5/raw/motion_walk_0.6ms.csv`. `F1_29DOF_physically_mirrored.urdf` remains an alternate model variant unless a training config explicitly opts into it.

## Retargeted Reference Motions

```text
resources/motions/f1/v1.5/
├── metadata.json
├── raw/         retargeted motion CSV files (e.g. 07_03_walk_yup_recwalk_..._minima_safe.csv)
└── processed/   NPZ files generated from raw CSVs
```

Processing pipeline:

```text
raw/*.csv  --(humanoid/scripts/preprocess_motion_csv.py)-->  processed/*.npz
```

## Related Code

- `humanoid/scripts/preprocess_motion_csv.py`: converts retargeted motion CSV to NPZ.
- `humanoid/utils/motion_loader.py`: torch-backed loader for processed reference motions.
- `humanoid/envs/f1/f1_dh_stand_config.py`: references the retargeted first-frame pose and per-DOF scales.

## Maintenance

When adding a new URDF variant or motion clip, keep the directory conventions above and update this document if the structure changes. Register only the pointer to this document in `AGENTS.md`.
