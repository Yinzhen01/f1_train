import argparse
import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


ROOT_COLUMNS = [
    "root_pos_x",
    "root_pos_y",
    "root_pos_z",
    "root_quat_x",
    "root_quat_y",
    "root_quat_z",
    "root_quat_w",
]


def _load_urdf_joint_names(urdf_path):
    root = ET.parse(urdf_path).getroot()
    return [
        joint.attrib["name"]
        for joint in root.findall("joint")
        if joint.attrib.get("type") != "fixed"
    ]


def _normalize_quat(quat):
    norm = np.linalg.norm(quat, axis=1, keepdims=True)
    if np.any(norm <= 0):
        raise ValueError("Encountered zero-length quaternion")
    quat = quat / norm
    for i in range(1, quat.shape[0]):
        if np.dot(quat[i - 1], quat[i]) < 0:
            quat[i] *= -1.0
    return quat


def _quat_inv(q):
    out = q.copy()
    out[..., :3] *= -1.0
    return out


def _quat_mul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack(
        (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ),
        axis=-1,
    )


def _quat_to_rotvec(q):
    q = q.copy()
    sign = np.where(q[..., 3:4] < 0, -1.0, 1.0)
    q *= sign
    xyz = q[..., :3]
    w = np.clip(q[..., 3], -1.0, 1.0)
    sin_half = np.linalg.norm(xyz, axis=-1)
    angle = 2.0 * np.arctan2(sin_half, w)
    scale = np.zeros_like(angle)
    mask = sin_half > 1e-12
    scale[mask] = angle[mask] / sin_half[mask]
    return xyz * scale[..., None]


def _finite_difference(values, timestamps):
    return np.gradient(values, timestamps, axis=0, edge_order=2)


def _angular_velocity(quat, timestamps):
    if quat.shape[0] < 2:
        return np.zeros((quat.shape[0], 3), dtype=np.float32)

    segment_dt = np.diff(timestamps)
    if np.any(segment_dt <= 0):
        raise ValueError("Timestamps must be strictly increasing")

    q_delta = _quat_mul(quat[1:], _quat_inv(quat[:-1]))
    segment_omega = _quat_to_rotvec(q_delta) / segment_dt[:, None]
    omega = np.empty((quat.shape[0], 3), dtype=np.float64)
    omega[0] = segment_omega[0]
    omega[-1] = segment_omega[-1]
    if quat.shape[0] > 2:
        left_dt = segment_dt[:-1]
        right_dt = segment_dt[1:]
        omega[1:-1] = (
            segment_omega[:-1] * left_dt[:, None]
            + segment_omega[1:] * right_dt[:, None]
        ) / (left_dt + right_dt)[:, None]
    return omega.astype(np.float32)


def _read_motion_csv(csv_path):
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        raise ValueError(f"No data rows in {csv_path}")
    return header, rows


def preprocess(csv_path, urdf_path, output_path, metadata_path):
    header, rows = _read_motion_csv(csv_path)
    joint_names = _load_urdf_joint_names(urdf_path)
    expected_header = ["timestamp"] + ROOT_COLUMNS + joint_names
    if header != expected_header:
        raise ValueError(
            "CSV columns do not match expected F1 motion schema.\n"
            f"Expected: {expected_header}\n"
            f"Actual:   {header}"
        )

    timestamps = np.array([float(row["timestamp"]) for row in rows], dtype=np.float64)
    if timestamps.shape[0] < 3:
        raise ValueError("At least 3 frames are required for edge-order finite differences")
    if np.any(np.diff(timestamps) <= 0):
        raise ValueError("Timestamps must be strictly increasing")

    root_pos = np.array(
        [[float(row[name]) for name in ROOT_COLUMNS[:3]] for row in rows],
        dtype=np.float32,
    )
    root_quat = np.array(
        [[float(row[name]) for name in ROOT_COLUMNS[3:]] for row in rows],
        dtype=np.float64,
    )
    root_quat = _normalize_quat(root_quat).astype(np.float32)
    dof_pos = np.array(
        [[float(row[name]) for name in joint_names] for row in rows],
        dtype=np.float32,
    )

    root_lin_vel = _finite_difference(root_pos.astype(np.float64), timestamps).astype(np.float32)
    dof_vel = _finite_difference(dof_pos.astype(np.float64), timestamps).astype(np.float32)
    root_ang_vel = _angular_velocity(root_quat.astype(np.float64), timestamps)

    dt = np.diff(timestamps)
    mean_dt = float(np.mean(dt))
    fps = float(1.0 / mean_dt)
    duration = float(timestamps[-1] - timestamps[0])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        timestamps=timestamps.astype(np.float32),
        root_pos=root_pos,
        root_quat=root_quat,
        root_lin_vel=root_lin_vel,
        root_ang_vel=root_ang_vel,
        dof_pos=dof_pos,
        dof_vel=dof_vel,
        joint_names=np.array(joint_names),
        fps=np.array(fps, dtype=np.float32),
        dt=np.array(mean_dt, dtype=np.float32),
        duration=np.array(duration, dtype=np.float32),
        source_csv=np.array(str(csv_path.as_posix())),
        robot_urdf=np.array(str(urdf_path.as_posix())),
    )

    metadata = {
        "source_csv": str(csv_path.as_posix()),
        "processed_npz": str(output_path.as_posix()),
        "robot_urdf": str(urdf_path.as_posix()),
        "frame_count": int(timestamps.shape[0]),
        "joint_count": int(len(joint_names)),
        "fps": fps,
        "dt": mean_dt,
        "duration": duration,
        "timestamp_start": float(timestamps[0]),
        "timestamp_end": float(timestamps[-1]),
        "joint_names": joint_names,
        "root_columns": ROOT_COLUMNS,
        "notes": [
            "CSV joint columns are expected to match the F1 v1.5 URDF actuated joint order.",
            "left_wrist_roll_joint and right_wrist_roll_joint are zero-filled in the raw CSV.",
            "neck_motor_base_pitch_joint and head_face_bracket_pitch_joint were dropped before preprocessing.",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Preprocess F1 retargeted motion CSV to NPZ.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--urdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()

    metadata = preprocess(args.csv, args.urdf, args.output, args.metadata)
    print(
        "processed "
        f"{metadata['frame_count']} frames, "
        f"{metadata['joint_count']} joints, "
        f"fps={metadata['fps']:.6f}, "
        f"duration={metadata['duration']:.6f}s"
    )


if __name__ == "__main__":
    main()
