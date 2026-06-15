"""Scale left_hip_roll excursions that exceed the URDF limit (+0.2 rad).

Method: within each violation window (expanded to where the joint falls back
to ~pivot), scale the part above the pivot toward a target peak with a
cosine-blended factor, so there is no truncation and no flat-top. Optionally
compensate left_ankle_roll to keep the foot orientation unchanged (validated
via MuJoCo FK by the render script).

Windows were identified from analysis of
07_03_walk_yup_recwalk_base_lowerbody_smooth_p8_120_180_groundfit_minima_safe.csv:
  frames  35-151 (t=1.17-5.03s, peak +0.241)
  frames 206-295 (t=6.87-9.83s, peak +0.220)
  frames 346-414 (t=11.53-13.80s, peak +0.224, no fade-out: clip ends high)
"""

import argparse
from pathlib import Path

import numpy as np

PIVOT = 0.05          # rad; only the part above this is scaled
TARGET_PEAK = 0.19    # rad; 5% margin below the +0.2 limit
RAMP_FRAMES = 10      # cosine ramp length at window edges (~0.33 s @ 30 fps)

# (start_frame, end_frame_inclusive, fade_out)
WINDOWS = [
    (35, 151, True),
    (206, 295, True),
    (346, 414, False),
]


def cosine_weight(n, ramp, fade_in=True, fade_out=True):
    """Bump weight: 0 -> 1 -> 0 with cosine ramps of length `ramp`."""
    w = np.ones(n)
    r = min(ramp, n // 2)
    if fade_in and r > 0:
        w[:r] = 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, r)))
    if fade_out and r > 0:
        w[-r:] = 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, r)))
    return w


def scale_joint(q, windows=WINDOWS, pivot=PIVOT, target=TARGET_PEAK,
                ramp=RAMP_FRAMES):
    """Return scaled copy of q and per-frame delta (q_new - q)."""
    q_new = q.copy()
    for a, b, fade_out in windows:
        seg = q[a:b + 1]
        peak = seg.max()
        if peak <= target:
            continue
        k_min = (target - pivot) / (peak - pivot)
        w = cosine_weight(len(seg), ramp, fade_in=True, fade_out=fade_out)
        k = 1.0 - (1.0 - k_min) * w
        above = seg > pivot
        out = seg.copy()
        out[above] = pivot + k[above] * (seg[above] - pivot)
        q_new[a:b + 1] = out
    return q_new, q_new - q


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compensate-ankle", action="store_true",
                        help="apply +delta to left_ankle_roll to preserve "
                             "foot orientation (sign validated via MuJoCo FK)")
    args = parser.parse_args()

    header = args.csv.read_text(encoding="utf-8").splitlines()[0].split(",")
    data = np.genfromtxt(args.csv, delimiter=",", skip_header=1)

    j_hip = header.index("left_hip_roll_joint")
    j_ankle = header.index("left_ankle_roll_joint")

    q_new, delta = scale_joint(data[:, j_hip])
    data[:, j_hip] = q_new
    if args.compensate_ankle:
        data[:, j_ankle] = data[:, j_ankle] + delta

    n_over = int((q_new > 0.2).sum())
    print(f"left_hip_roll: new range [{q_new.min():+.4f}, {q_new.max():+.4f}], "
          f"frames >0.2: {n_over}, max |delta| {np.abs(delta).max():.4f} rad, "
          f"ankle compensation: {args.compensate_ankle}")

    fmt = ",".join(["%.10g"] * data.shape[1])
    np.savetxt(args.output, data, delimiter=",", fmt=fmt,
               header=",".join(header), comments="")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
