#!/usr/bin/env python3
"""Add MuJoCo FK body positions to a retargeted motion NPZ.

The output keeps all original NPZ arrays and adds:

    body_names: [num_selected_bodies]
    body_pos:   [num_frames, num_selected_bodies, 3]

These body positions can be used by spatial imitation rewards and diagnostics
when the motion-imitation training profile enables body_pos keypoints.
"""

from __future__ import annotations

import argparse
import copy
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import mujoco


DEFAULT_BODY_TOKENS = ()
DEFAULT_EXCLUDE_BODY_TOKENS = (
    "wrist",
)


def _select_body_names(
    model: mujoco.MjModel,
    tokens: tuple[str, ...],
    exclude_tokens: tuple[str, ...],
) -> list[str]:
    names = []
    for body_id in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if not name:
            continue
        if exclude_tokens and any(token in name for token in exclude_tokens):
            continue
        if not tokens or any(token in name for token in tokens):
            names.append(name)
    if not names:
        raise ValueError(f"No MuJoCo bodies matched tokens: {tokens}")
    return names


def _joint_qpos_addresses(model: mujoco.MjModel, joint_names: list[str]) -> np.ndarray:
    addresses = []
    missing = []
    for name in joint_names:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            missing.append(name)
            continue
        addresses.append(model.jnt_qposadr[joint_id])
    if missing:
        raise ValueError(f"MJCF is missing joints from motion NPZ: {missing}")
    return np.asarray(addresses, dtype=np.int64)


def _rewrite_meshdir_for_parent(root: ET.Element, source_parent: Path, target_parent: Path) -> None:
    for compiler in root.findall("compiler"):
        meshdir = compiler.attrib.get("meshdir")
        if not meshdir:
            continue
        mesh_path = (source_parent / meshdir).resolve()
        if not mesh_path.exists():
            for parent in (source_parent, *source_parent.parents):
                candidate = parent / "meshes"
                if candidate.exists():
                    mesh_path = candidate.resolve()
                    break
        compiler.attrib["meshdir"] = os.path.relpath(mesh_path, target_parent)


def _inline_includes(root: ET.Element, source_parent: Path, target_parent: Path) -> None:
    children = list(root)
    for child in children:
        if child.tag != "include":
            _inline_includes(child, source_parent, target_parent)
            continue

        include_file = child.attrib.get("file")
        if not include_file:
            continue
        include_path = (source_parent / include_file).resolve()
        include_tree = ET.parse(include_path)
        include_root = include_tree.getroot()
        include_parent = include_path.parent
        _inline_includes(include_root, include_parent, target_parent)
        _rewrite_meshdir_for_parent(include_root, include_parent, target_parent)

        insert_at = list(root).index(child)
        root.remove(child)
        for included_child in list(include_root):
            root.insert(insert_at, copy.deepcopy(included_child))
            insert_at += 1


def _load_mujoco_model(mjcf: Path) -> mujoco.MjModel:
    try:
        return mujoco.MjModel.from_xml_path(str(mjcf))
    except ValueError as exc:
        match = re.search(r"unrecognized attribute: '([^']+)'", str(exc))
        if match is None:
            raise

    tree = ET.parse(mjcf)
    root = tree.getroot()
    _inline_includes(root, mjcf.parent, mjcf.parent)
    for compiler in root.findall("compiler"):
        compiler.attrib.setdefault("autolimits", "true")
        meshdir = compiler.attrib.get("meshdir")
        if meshdir and (mjcf.parent / meshdir).exists():
            continue
        for parent in (mjcf.parent, *mjcf.parents):
            candidate = parent / "meshes"
            if candidate.exists():
                compiler.attrib["meshdir"] = os.path.relpath(candidate, mjcf.parent)
                break
    with tempfile.NamedTemporaryFile(
        "w",
        suffix=".xml",
        dir=mjcf.parent,
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp_path = Path(tmp.name)
    unknown_attr = match.group(1)
    try:
        for _ in range(20):
            removed = 0
            for elem in root.iter():
                if unknown_attr in elem.attrib:
                    del elem.attrib[unknown_attr]
                    removed += 1
            if removed == 0:
                raise ValueError(f"Could not remove unknown MuJoCo XML attribute: {unknown_attr}")
            tree.write(tmp_path, encoding="unicode")
            try:
                return mujoco.MjModel.from_xml_path(str(tmp_path))
            except ValueError as exc:
                match = re.search(r"unrecognized attribute: '([^']+)'", str(exc))
                if match is None:
                    raise
                unknown_attr = match.group(1)
        raise ValueError("Too many MuJoCo XML compatibility retries")
    finally:
        tmp_path.unlink(missing_ok=True)


def augment_motion(
    input_npz: Path,
    mjcf: Path,
    output_npz: Path,
    body_tokens: tuple[str, ...],
    exclude_body_tokens: tuple[str, ...],
) -> None:
    data = np.load(input_npz, allow_pickle=False)
    model = _load_mujoco_model(mjcf)
    mdata = mujoco.MjData(model)

    joint_names = [str(name) for name in data["joint_names"].tolist()]
    qpos_addresses = _joint_qpos_addresses(model, joint_names)
    body_names = _select_body_names(model, body_tokens, exclude_body_tokens)
    body_ids = np.asarray(
        [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) for name in body_names],
        dtype=np.int64,
    )

    frame_count = data["timestamps"].shape[0]
    body_pos = np.zeros((frame_count, len(body_names), 3), dtype=np.float32)
    for frame_idx in range(frame_count):
        mdata.qpos[0:3] = data["root_pos"][frame_idx]
        # MuJoCo free-joint qpos quaternion order is w, x, y, z.
        root_quat_xyzw = data["root_quat"][frame_idx]
        mdata.qpos[3] = root_quat_xyzw[3]
        mdata.qpos[4:7] = root_quat_xyzw[0:3]
        mdata.qpos[qpos_addresses] = data["dof_pos"][frame_idx]
        mujoco.mj_forward(model, mdata)
        body_pos[frame_idx] = mdata.xpos[body_ids]

    payload = {key: data[key] for key in data.files if key not in ("body_names", "body_pos")}
    payload["body_names"] = np.asarray(body_names)
    payload["body_pos"] = body_pos
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output_npz, **payload)

    print(f"wrote {output_npz}")
    print(f"frames={frame_count} bodies={len(body_names)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Input motion NPZ")
    parser.add_argument("--mjcf", required=True, type=Path, help="MuJoCo XML matching the motion")
    parser.add_argument("--output", required=True, type=Path, help="Output augmented NPZ")
    parser.add_argument(
        "--body-token",
        action="append",
        dest="body_tokens",
        help="Body-name token to include. May be repeated. Defaults to all named bodies.",
    )
    parser.add_argument(
        "--exclude-body-token",
        action="append",
        dest="exclude_body_tokens",
        help="Body-name token to exclude. May be repeated. Defaults to wrist.",
    )
    args = parser.parse_args()
    body_tokens = tuple(args.body_tokens) if args.body_tokens else DEFAULT_BODY_TOKENS
    exclude_body_tokens = (
        tuple(args.exclude_body_tokens)
        if args.exclude_body_tokens is not None
        else DEFAULT_EXCLUDE_BODY_TOKENS
    )
    augment_motion(args.input, args.mjcf, args.output, body_tokens, exclude_body_tokens)


if __name__ == "__main__":
    main()
