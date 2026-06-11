import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import torch

from humanoid import LEGGED_GYM_ROOT_DIR


MOTION_TENSOR_KEYS = (
    "root_pos",
    "root_quat",
    "root_lin_vel",
    "root_ang_vel",
    "dof_pos",
    "dof_vel",
)

OPTIONAL_MOTION_TENSOR_KEYS = (
    "foot_contacts",
)


def load_urdf_actuated_joint_names(urdf_path: str) -> list:
    """Return non-fixed URDF joint names in asset order."""
    path = Path(urdf_path.format(LEGGED_GYM_ROOT_DIR=LEGGED_GYM_ROOT_DIR))
    root = ET.parse(path).getroot()
    return [
        joint.attrib["name"]
        for joint in root.findall("joint")
        if joint.attrib.get("type") != "fixed"
    ]


class MotionLoader:
    """Torch-backed reference motion loader for retargeted humanoid motions."""

    def __init__(
        self,
        motion_file: str,
        device: str,
        expected_joint_names: Optional[Iterable[str]] = None,
    ):
        self.motion_file = Path(motion_file.format(LEGGED_GYM_ROOT_DIR=LEGGED_GYM_ROOT_DIR))
        self.device = torch.device(device)

        data = np.load(self.motion_file, allow_pickle=False)
        self.joint_names = [str(name) for name in data["joint_names"].tolist()]
        if expected_joint_names is not None:
            expected = list(expected_joint_names)
            if self.joint_names != expected:
                if set(self.joint_names) != set(expected):
                    raise ValueError(
                        "Motion joint_names do not match expected joints.\n"
                        f"Expected: {expected}\n"
                        f"Actual:   {self.joint_names}"
                    )
                self._joint_reorder_indices = [self.joint_names.index(name) for name in expected]
                self.joint_names = expected
            else:
                self._joint_reorder_indices = None
        else:
            self._joint_reorder_indices = None

        self.frame_count = int(data["timestamps"].shape[0])
        if self.frame_count < 2:
            raise ValueError(f"Motion requires at least 2 frames: {self.motion_file}")

        self.timestamps = torch.as_tensor(
            data["timestamps"], dtype=torch.float32, device=self.device
        )
        self.dt = float(data["dt"])
        self.fps = float(data["fps"])
        self.duration = float(data["duration"])
        if self.duration <= 0.0:
            raise ValueError(f"Motion duration must be positive: {self.motion_file}")

        self.tensors: Dict[str, torch.Tensor] = {}
        for key in MOTION_TENSOR_KEYS:
            value = torch.as_tensor(data[key], dtype=torch.float32, device=self.device)
            if key in ("dof_pos", "dof_vel") and self._joint_reorder_indices is not None:
                value = value[:, self._joint_reorder_indices]
            if value.shape[0] != self.frame_count:
                raise ValueError(
                    f"Motion key {key} has {value.shape[0]} frames, expected {self.frame_count}"
                )
            self.tensors[key] = value
        for key in OPTIONAL_MOTION_TENSOR_KEYS:
            if key not in data.files:
                continue
            value = torch.as_tensor(data[key], dtype=torch.float32, device=self.device)
            if value.shape[0] != self.frame_count:
                raise ValueError(
                    f"Motion key {key} has {value.shape[0]} frames, expected {self.frame_count}"
                )
            self.tensors[key] = value

        self._validate_shapes()

    def _validate_shapes(self):
        if self.tensors["root_pos"].shape[1] != 3:
            raise ValueError("root_pos must have shape [T, 3]")
        if self.tensors["root_quat"].shape[1] != 4:
            raise ValueError("root_quat must have shape [T, 4]")
        if self.tensors["dof_pos"].shape[1] != len(self.joint_names):
            raise ValueError("dof_pos width must match joint_names")
        if self.tensors["dof_vel"].shape != self.tensors["dof_pos"].shape:
            raise ValueError("dof_vel shape must match dof_pos")
        if "foot_contacts" in self.tensors and self.tensors["foot_contacts"].shape[1] != 2:
            raise ValueError("foot_contacts must have shape [T, 2]")

    def sample_by_phase(self, phase: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Sample reference state at normalized phase in [0, 1)."""
        return self.sample_by_time(torch.remainder(phase, 1.0) * self.duration)

    def sample_by_time(self, times: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Sample reference state at wrapped motion times in seconds."""
        times = torch.as_tensor(times, dtype=torch.float32, device=self.device)
        flat_times = torch.remainder(times.reshape(-1), self.duration)

        frame_pos = flat_times / self.dt
        idx0 = torch.floor(frame_pos).long().clamp(0, self.frame_count - 1)
        idx1 = (idx0 + 1) % self.frame_count
        alpha = (frame_pos - idx0.float()).clamp(0.0, 1.0).unsqueeze(-1)

        samples = {}
        for key, values in self.tensors.items():
            interp = values[idx0] * (1.0 - alpha) + values[idx1] * alpha
            if key == "root_quat":
                interp = torch.nn.functional.normalize(interp, dim=-1)
            samples[key] = interp.reshape(*times.shape, values.shape[-1])
        samples["phase"] = torch.remainder(flat_times / self.duration, 1.0).reshape(times.shape)
        samples["frame_index"] = idx0.reshape(times.shape)
        return samples

    def get_frame(self, frame_ids: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Return exact reference frames by wrapped integer frame id."""
        frame_ids = torch.as_tensor(frame_ids, dtype=torch.long, device=self.device)
        frame_ids = torch.remainder(frame_ids, self.frame_count)
        samples = {
            key: values[frame_ids]
            for key, values in self.tensors.items()
        }
        samples["phase"] = (frame_ids.float() / self.frame_count)
        samples["frame_index"] = frame_ids
        return samples
