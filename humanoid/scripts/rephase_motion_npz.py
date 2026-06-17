#!/usr/bin/env python3
"""Rephase a retargeted motion NPZ so a stable double-support frame starts it."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


ANKLE_NAME_CANDIDATES = {
    "left": ("left_ankle_roll_link", "left_ankle_pitch_link"),
    "right": ("right_ankle_roll_link", "right_ankle_pitch_link"),
}


def _quat_to_roll_pitch(quat_xyzw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x, y, z, w = np.moveaxis(quat_xyzw, -1, 0)
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    pitch = np.arcsin(np.clip(sinp, -1.0, 1.0))
    return roll, pitch


def _body_index(body_names: list[str], side: str) -> int:
    for name in ANKLE_NAME_CANDIDATES[side]:
        if name in body_names:
            return body_names.index(name)
    candidates = [name for name in body_names if side in name and "ankle" in name]
    if candidates:
        return body_names.index(candidates[0])
    raise ValueError(f"Could not find {side} ankle body in body_names")


def _rotated(values: np.ndarray, start_frame: int, frame_count: int) -> np.ndarray:
    if values.shape[:1] != (frame_count,):
        return values
    return np.concatenate((values[start_frame:], values[:start_frame]), axis=0)


def _reset_timestamps(payload: dict[str, np.ndarray], frame_count: int) -> None:
    dt = float(np.asarray(payload["dt"]))
    payload["timestamps"] = (np.arange(frame_count, dtype=np.float32) * dt).astype(np.float32)
    payload["duration"] = np.asarray(float((frame_count - 1) * dt), dtype=np.float32)
    payload["fps"] = np.asarray(float(1.0 / dt), dtype=np.float32)


def _infer_foot_contacts(
    left_z: np.ndarray,
    right_z: np.ndarray,
    dt: float,
    height_margin: float,
    max_abs_vz: float,
) -> np.ndarray:
    left_vz = np.gradient(left_z, dt, edge_order=2)
    right_vz = np.gradient(right_z, dt, edge_order=2)
    left_contact = (left_z <= left_z.min() + height_margin) & (np.abs(left_vz) <= max_abs_vz)
    right_contact = (right_z <= right_z.min() + height_margin) & (np.abs(right_vz) <= max_abs_vz)
    return np.stack((left_contact, right_contact), axis=1).astype(np.float32)


def choose_start_frame(
    data: np.lib.npyio.NpzFile,
    min_frame: int,
    max_frame: int | None,
    height_gap_weight: float,
    foot_vz_weight: float,
    tilt_weight: float,
    root_y_vel_weight: float,
) -> tuple[int, dict[str, float]]:
    if "body_pos" not in data.files or "body_names" not in data.files:
        raise ValueError("Input NPZ must contain body_pos and body_names")

    body_names = [str(name) for name in data["body_names"].tolist()]
    left_idx = _body_index(body_names, "left")
    right_idx = _body_index(body_names, "right")
    body_pos = data["body_pos"]
    left_z = body_pos[:, left_idx, 2]
    right_z = body_pos[:, right_idx, 2]
    dt = float(np.asarray(data["dt"]))
    left_vz = np.gradient(left_z, dt, edge_order=2)
    right_vz = np.gradient(right_z, dt, edge_order=2)
    roll, pitch = _quat_to_roll_pitch(data["root_quat"])
    root_lin_vel = data["root_lin_vel"]

    frame_count = left_z.shape[0]
    end = frame_count if max_frame is None else min(max_frame, frame_count)
    if min_frame < 0 or min_frame >= end:
        raise ValueError(f"Invalid search range: min_frame={min_frame}, max_frame={max_frame}")

    both_low = np.maximum(left_z - left_z.min(), right_z - right_z.min())
    height_gap = np.abs(left_z - right_z)
    foot_vz = np.abs(left_vz) + np.abs(right_vz)
    tilt = np.abs(roll) + np.abs(pitch)
    root_y_vel = np.abs(root_lin_vel[:, 1])
    score = (
        both_low
        + height_gap_weight * height_gap
        + foot_vz_weight * foot_vz
        + tilt_weight * tilt
        + root_y_vel_weight * root_y_vel
    )

    search_slice = slice(min_frame, end)
    start_frame = int(np.argmin(score[search_slice]) + min_frame)
    info = {
        "score": float(score[start_frame]),
        "left_ankle_z": float(left_z[start_frame]),
        "right_ankle_z": float(right_z[start_frame]),
        "left_ankle_vz": float(left_vz[start_frame]),
        "right_ankle_vz": float(right_vz[start_frame]),
        "root_roll": float(roll[start_frame]),
        "root_pitch": float(pitch[start_frame]),
        "root_lin_vel_y": float(root_lin_vel[start_frame, 1]),
    }
    return start_frame, info


def rephase_motion(
    input_npz: Path,
    output_npz: Path,
    start_frame: int | None,
    min_frame: int,
    max_frame: int | None,
    add_foot_contacts: bool,
    contact_height_margin: float,
    contact_max_abs_vz: float,
) -> None:
    data = np.load(input_npz, allow_pickle=False)
    frame_count = int(data["timestamps"].shape[0])
    if start_frame is None:
        start_frame, info = choose_start_frame(
            data,
            min_frame=min_frame,
            max_frame=max_frame,
            height_gap_weight=2.0,
            foot_vz_weight=0.25,
            tilt_weight=0.15,
            root_y_vel_weight=0.15,
        )
    else:
        if start_frame < 0 or start_frame >= frame_count:
            raise ValueError(f"start_frame={start_frame} is outside frame_count={frame_count}")
        _, info = choose_start_frame(
            data,
            min_frame=start_frame,
            max_frame=start_frame + 1,
            height_gap_weight=2.0,
            foot_vz_weight=0.25,
            tilt_weight=0.15,
            root_y_vel_weight=0.15,
        )

    payload = {
        key: _rotated(data[key], start_frame, frame_count)
        for key in data.files
        if key not in ("timestamps", "duration", "fps")
    }
    payload["source_npz"] = np.asarray(str(input_npz.as_posix()))
    payload["rephase_start_frame"] = np.asarray(start_frame, dtype=np.int32)
    for key, value in info.items():
        payload[f"rephase_{key}"] = np.asarray(value, dtype=np.float32)
    _reset_timestamps(payload, frame_count)

    if add_foot_contacts:
        body_names = [str(name) for name in payload["body_names"].tolist()]
        left_idx = _body_index(body_names, "left")
        right_idx = _body_index(body_names, "right")
        body_pos = payload["body_pos"]
        payload["foot_contacts"] = _infer_foot_contacts(
            body_pos[:, left_idx, 2],
            body_pos[:, right_idx, 2],
            dt=float(np.asarray(payload["dt"])),
            height_margin=contact_height_margin,
            max_abs_vz=contact_max_abs_vz,
        )

    output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_npz, **payload)
    print(f"wrote {output_npz}")
    print(f"frames={frame_count} start_frame={start_frame}")
    for key, value in info.items():
        print(f"{key}={value:.6f}")
    if add_foot_contacts:
        contacts = payload["foot_contacts"]
        print(
            "foot_contact_ratio="
            f"left:{contacts[:, 0].mean():.3f} right:{contacts[:, 1].mean():.3f} "
            f"double:{np.logical_and(contacts[:, 0] > 0.5, contacts[:, 1] > 0.5).mean():.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start-frame", type=int)
    parser.add_argument("--min-frame", type=int, default=0)
    parser.add_argument("--max-frame", type=int)
    parser.add_argument("--add-foot-contacts", action="store_true")
    parser.add_argument("--contact-height-margin", type=float, default=0.025)
    parser.add_argument("--contact-max-abs-vz", type=float, default=0.20)
    args = parser.parse_args()

    rephase_motion(
        input_npz=args.input,
        output_npz=args.output,
        start_frame=args.start_frame,
        min_frame=args.min_frame,
        max_frame=args.max_frame,
        add_foot_contacts=args.add_foot_contacts,
        contact_height_margin=args.contact_height_margin,
        contact_max_abs_vz=args.contact_max_abs_vz,
    )


if __name__ == "__main__":
    main()
