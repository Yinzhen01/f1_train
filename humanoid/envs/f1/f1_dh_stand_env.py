# Copyright (c) 2024, AgiBot Inc. All rights reserved.

import math
import xml.etree.ElementTree as ET

import torch
from isaacgym import gymtorch
from isaacgym.torch_utils import quat_rotate, quat_rotate_inverse

from humanoid import LEGGED_GYM_ROOT_DIR
from humanoid.envs.base.legged_robot import get_euler_xyz_tensor
from humanoid.envs.x1.x1_dh_stand_env import X1DHStandEnv
from humanoid.utils.motion_loader import MotionLoader


def _quat_conjugate(quat):
    out = quat.clone()
    out[..., :3] *= -1.0
    return out


def _quat_mul(a, b):
    ax, ay, az, aw = torch.unbind(a, dim=-1)
    bx, by, bz, bw = torch.unbind(b, dim=-1)
    return torch.stack(
        (
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ),
        dim=-1,
    )


def _quat_rotate_py(quat, vec):
    x, y, z, w = quat
    vx, vy, vz = vec
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def _quat_mul_py(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def _quat_from_rpy(rpy):
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _compose_transform(pos_a, quat_a, pos_b, quat_b):
    rotated = _quat_rotate_py(quat_a, pos_b)
    pos = tuple(pos_a[i] + rotated[i] for i in range(3))
    quat = _quat_mul_py(quat_a, quat_b)
    return pos, quat


class F1DHStandEnv(X1DHStandEnv):
    """F1 29-DOF variant of the X1 walking environment."""

    def _init_buffers(self):
        super()._init_buffers()
        self.motion_loader = None
        self.motion_time_offsets = torch.zeros(self.num_envs, device=self.device)
        self.ref_action = torch.zeros((self.num_envs, self.num_actions), device=self.device)
        self.ref_dof_vel = torch.zeros_like(self.dof_vel)
        self.ref_joint_pos_error = torch.zeros_like(self.dof_pos)
        self.ref_joint_pos_error_max = torch.zeros(self.num_envs, device=self.device)
        self.ref_root_pos = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_root_pos_offset = torch.zeros((self.num_envs, 3), device=self.device)
        self.aligned_ref_root_pos = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_root_quat = torch.zeros((self.num_envs, 4), device=self.device)
        self.ref_root_quat[:, 3] = 1.0
        self.ref_root_lin_vel = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_root_ang_vel = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_foot_contacts = None
        self.ref_body_pos = None
        self.body_pos_world = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.aligned_ref_body_pos_world = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.body_pos_local = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.ref_body_pos_local = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.ref_body_pos_local_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.ref_body_pos_local_error = torch.zeros((self.num_envs, 0), device=self.device)
        self.ref_body_pos_world_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.ref_body_pos_world_error = torch.zeros((self.num_envs, 0), device=self.device)
        self.ref_body_pos_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
        self.ref_body_pos_error = torch.zeros((self.num_envs, 0), device=self.device)
        self.ref_body_pos_error_mean = torch.zeros(self.num_envs, device=self.device)
        self.ref_body_pos_error_max = torch.zeros(self.num_envs, device=self.device)
        self.termination_world_keypoint_buf = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        self.world_keypoint_termination_error_max = torch.zeros(self.num_envs, device=self.device)
        self.ref_body_pos_names = []
        self.ref_body_pos_body_indices = torch.zeros(0, dtype=torch.long, device=self.device)
        self.ref_body_pos_motion_indices = torch.zeros(0, dtype=torch.long, device=self.device)
        self.ref_virtual_body_pos_names = []
        self.ref_virtual_body_pos_parent_indices = torch.zeros(0, dtype=torch.long, device=self.device)
        self.ref_virtual_body_pos_motion_indices = torch.zeros(0, dtype=torch.long, device=self.device)
        self.ref_virtual_body_pos_offsets = torch.zeros((0, 3), device=self.device)

        motion_cfg = getattr(self.cfg, "motion_reference", None)
        if motion_cfg is None or not motion_cfg.enabled:
            return

        self.motion_loader = MotionLoader(
            motion_cfg.file,
            device=self.device,
            expected_joint_names=self.dof_names,
        )
        start_time_offset = float(getattr(motion_cfg, "start_time_offset", 0.0))
        if motion_cfg.randomize_start_phase:
            self.motion_time_offsets = (
                torch.rand(self.num_envs, device=self.device) * self.motion_loader.duration
                + start_time_offset
            )
        else:
            self.motion_time_offsets[:] = start_time_offset
        self._init_ref_body_pos_indices()

    def _init_ref_body_pos_indices(self):
        if self.motion_loader is None or self.motion_loader.body_names is None:
            return
        body_names = getattr(self, "body_names", [])
        body_name_to_idx = {name: idx for idx, name in enumerate(body_names)}
        motion_indices = []
        body_indices = []
        names = []
        virtual_motion_indices = []
        virtual_parent_indices = []
        virtual_offsets = []
        virtual_names = []
        fixed_body_offsets = self._load_fixed_body_offsets(body_name_to_idx)
        for motion_idx, name in enumerate(self.motion_loader.body_names):
            if name not in body_name_to_idx:
                fixed_offset = fixed_body_offsets.get(name)
                if fixed_offset is not None:
                    parent_name, local_pos = fixed_offset
                    virtual_motion_indices.append(motion_idx)
                    virtual_parent_indices.append(body_name_to_idx[parent_name])
                    virtual_offsets.append(local_pos)
                    virtual_names.append(name)
                continue
            motion_indices.append(motion_idx)
            body_indices.append(body_name_to_idx[name])
            names.append(name)
        if not names and not virtual_names:
            return
        self.ref_body_pos_names = names + virtual_names
        if motion_indices:
            self.ref_body_pos_motion_indices = torch.tensor(motion_indices, dtype=torch.long, device=self.device)
            self.ref_body_pos_body_indices = torch.tensor(body_indices, dtype=torch.long, device=self.device)
        if virtual_motion_indices:
            self.ref_virtual_body_pos_names = virtual_names
            self.ref_virtual_body_pos_motion_indices = torch.tensor(
                virtual_motion_indices, dtype=torch.long, device=self.device
            )
            self.ref_virtual_body_pos_parent_indices = torch.tensor(
                virtual_parent_indices, dtype=torch.long, device=self.device
            )
            self.ref_virtual_body_pos_offsets = torch.tensor(
                virtual_offsets, dtype=torch.float32, device=self.device
            )
        body_pos_shape = (self.num_envs, len(self.ref_body_pos_names))
        self.ref_body_pos_local_error = torch.zeros(body_pos_shape, device=self.device)
        self.ref_body_pos_world_error = torch.zeros(body_pos_shape, device=self.device)
        self.ref_body_pos_error = self.ref_body_pos_local_error

    def _load_fixed_body_offsets(self, body_name_to_idx):
        asset_file = self.cfg.asset.file.format(LEGGED_GYM_ROOT_DIR=LEGGED_GYM_ROOT_DIR)
        root = ET.parse(asset_file).getroot()
        fixed_children = {}
        for joint in root.findall("joint"):
            if joint.attrib.get("type") != "fixed":
                continue
            parent = joint.find("parent")
            child = joint.find("child")
            if parent is None or child is None:
                continue
            origin = joint.find("origin")
            xyz = (0.0, 0.0, 0.0)
            rpy = (0.0, 0.0, 0.0)
            if origin is not None:
                if "xyz" in origin.attrib:
                    xyz = tuple(float(value) for value in origin.attrib["xyz"].split())
                if "rpy" in origin.attrib:
                    rpy = tuple(float(value) for value in origin.attrib["rpy"].split())
            fixed_children[child.attrib["link"]] = (
                parent.attrib["link"],
                xyz,
                _quat_from_rpy(rpy),
            )

        offsets = {}
        for child_name in fixed_children:
            pos = (0.0, 0.0, 0.0)
            quat = (0.0, 0.0, 0.0, 1.0)
            current = child_name
            visited = set()
            chain = []
            while current in fixed_children and current not in visited:
                visited.add(current)
                parent_name, joint_pos, joint_quat = fixed_children[current]
                chain.append((parent_name, joint_pos, joint_quat))
                if parent_name in body_name_to_idx:
                    for _, chain_pos, chain_quat in reversed(chain):
                        pos, quat = _compose_transform(pos, quat, chain_pos, chain_quat)
                    offsets[child_name] = (parent_name, pos)
                    break
                current = parent_name
        return offsets

    def _reset_dofs(self, env_ids):
        if self.motion_loader is None or not self.cfg.motion_reference.reset_dofs_to_motion:
            return super()._reset_dofs(env_ids)

        samples = self.motion_loader.sample_by_time(self.motion_time_offsets[env_ids])
        self.dof_pos[env_ids] = samples["dof_pos"]
        self.dof_vel[env_ids] = samples["dof_vel"]

        env_ids_int32 = env_ids.to(dtype=torch.int32)
        self.gym.set_dof_state_tensor_indexed(
            self.sim,
            gymtorch.unwrap_tensor(self.dof_state),
            gymtorch.unwrap_tensor(env_ids_int32),
            len(env_ids_int32),
        )

    def _reset_root_states(self, env_ids):
        super()._reset_root_states(env_ids)
        if self.motion_loader is None:
            return

        motion_cfg = self.cfg.motion_reference
        if not (
            motion_cfg.reset_root_height
            or motion_cfg.reset_root_orientation
            or motion_cfg.reset_root_velocity
        ):
            return

        samples = self.motion_loader.sample_by_time(self.motion_time_offsets[env_ids])
        if motion_cfg.reset_root_height:
            self.root_states[env_ids, 2] = (
                self.env_origins[env_ids, 2] + samples["root_pos"][:, 2]
            )
        if motion_cfg.reset_root_orientation:
            self.root_states[env_ids, 3:7] = samples["root_quat"]
        if motion_cfg.reset_root_velocity:
            self.root_states[env_ids, 7:10] = samples["root_lin_vel"]
            self.root_states[env_ids, 10:13] = samples["root_ang_vel"]

        env_ids_int32 = env_ids.to(dtype=torch.int32)
        self.gym.set_actor_root_state_tensor_indexed(
            self.sim,
            gymtorch.unwrap_tensor(self.root_states),
            gymtorch.unwrap_tensor(env_ids_int32),
            len(env_ids_int32),
        )

    def reset_idx(self, env_ids):
        diagnostics = None
        if len(env_ids) > 0 and self.motion_loader is not None:
            diagnostics = self._collect_motion_episode_diagnostics(env_ids)
            motion_cfg = self.cfg.motion_reference
            if motion_cfg.randomize_start_phase:
                start_time_offset = float(getattr(motion_cfg, "start_time_offset", 0.0))
                self.motion_time_offsets[env_ids] = (
                    torch.rand(len(env_ids), device=self.device) * self.motion_loader.duration
                    + start_time_offset
                )
            else:
                self.motion_time_offsets[env_ids] = float(getattr(motion_cfg, "start_time_offset", 0.0))

        super().reset_idx(env_ids)
        if diagnostics is not None:
            self.extras.setdefault("episode", {}).update(diagnostics)
        if len(env_ids) > 0 and self.motion_loader is not None:
            self._apply_root_height_offset(env_ids)
            self._update_ref_root_pos_offsets(env_ids)

    def _collect_motion_episode_diagnostics(self, env_ids):
        motion_cfg = self.cfg.motion_reference
        duration = max(float(self.motion_loader.duration), 1e-6)
        motion_times = (
            self.phase_length_buf[env_ids].float() * self.dt * motion_cfg.playback_speed
            + self.motion_time_offsets[env_ids]
        )
        phase = torch.remainder(motion_times, duration) / duration
        episode_len = self.episode_length_buf[env_ids].float()
        policy_actions = getattr(self, "policy_actions", self.actions)[env_ids]
        action_abs = torch.abs(policy_actions)
        action_clip = float(getattr(self.cfg.normalization, "clip_actions", 100.0))
        saturation_threshold = 0.98 * action_clip

        diagnostics = {
            "motion_phase_reset_mean": torch.mean(phase),
            "motion_phase_reset_min": torch.min(phase),
            "motion_phase_reset_max": torch.max(phase),
            "motion_episode_length_mean": torch.mean(episode_len),
            "residual_action_abs_mean": torch.mean(action_abs),
            "residual_action_abs_max": torch.max(action_abs),
            "residual_action_saturation_rate": torch.mean((action_abs > saturation_threshold).float()),
            "ref_joint_error_mean": torch.mean(torch.abs(self.dof_pos[env_ids] - self.ref_dof_pos[env_ids])),
            "ref_joint_error_max": torch.mean(self.ref_joint_pos_error_max[env_ids]),
            "ref_vel_xy_error_mean": torch.mean(torch.norm(self.root_states[env_ids, 7:9] - self.ref_root_lin_vel[env_ids, :2], dim=1)),
            "base_height_reset_mean": torch.mean(self.root_states[env_ids, 2] - self.env_origins[env_ids, 2]),
            "base_height_reset_min": torch.min(self.root_states[env_ids, 2] - self.env_origins[env_ids, 2]),
            "ref_root_height_mean": torch.mean(self.aligned_ref_root_pos[env_ids, 2]),
        }

        phase_bin_count = 8
        phase_bins = torch.clamp((phase * phase_bin_count).long(), 0, phase_bin_count - 1)
        for bin_idx in range(phase_bin_count):
            diagnostics[f"motion_phase_reset_bin_{bin_idx}"] = torch.mean((phase_bins == bin_idx).float())

        reason_attrs = {
            "timeout": "time_out_buf",
            "base_contact": "termination_base_contact_buf",
            "height": "termination_height_buf",
            "roll": "termination_roll_buf",
            "pitch": "termination_pitch_buf",
            "ref_root_xy": "termination_ref_root_xy_buf",
            "ref_root_xyz": "termination_ref_root_xyz_buf",
            "ref_joint": "termination_ref_joint_pos_buf",
            "support_rect": "termination_support_rect_buf",
            "world_keypoint": "termination_world_keypoint_buf",
        }
        for label, attr in reason_attrs.items():
            values = getattr(self, attr, None)
            if values is not None:
                diagnostics[f"termination_{label}_rate"] = torch.mean(values[env_ids].float())

        if self.ref_body_pos_world_error.numel() > 0:
            diagnostics["ref_body_world_error_mean"] = torch.mean(self.ref_body_pos_error_mean[env_ids])
            diagnostics["ref_body_world_error_max"] = torch.mean(self.ref_body_pos_error_max[env_ids])
            for label, _, _ in getattr(self.cfg.rewards, "termination_world_keypoint_thresholds", ()):
                safe_label = str(label).replace("-", "_")
                rate = getattr(self, f"termination_world_keypoint_{safe_label}_buf", None)
                error = getattr(self, f"world_keypoint_{safe_label}_error_max", None)
                if rate is not None:
                    diagnostics[f"termination_world_keypoint_{safe_label}_rate"] = torch.mean(rate[env_ids].float())
                if error is not None:
                    diagnostics[f"world_keypoint_{safe_label}_error_max"] = torch.mean(error[env_ids])

        return diagnostics
    def _apply_root_height_offset(self, env_ids):
        motion_cfg = self.cfg.motion_reference
        root_height_offset = getattr(motion_cfg, "reset_root_height_offset", 0.0)
        if root_height_offset == 0.0:
            return

        self.root_states[env_ids, 2] += root_height_offset

        env_ids_int32 = env_ids.to(dtype=torch.int32)
        self.gym.set_actor_root_state_tensor_indexed(
            self.sim,
            gymtorch.unwrap_tensor(self.root_states),
            gymtorch.unwrap_tensor(env_ids_int32),
            len(env_ids_int32),
        )
        self.gym.refresh_actor_root_state_tensor(self.sim)

        self.base_quat[env_ids] = self.root_states[env_ids, 3:7]
        self.base_euler_xyz = get_euler_xyz_tensor(self.base_quat)
        self.projected_gravity[env_ids] = quat_rotate_inverse(
            self.base_quat[env_ids], self.gravity_vec[env_ids]
        )
        self.base_lin_vel[env_ids] = quat_rotate_inverse(
            self.base_quat[env_ids], self.root_states[env_ids, 7:10]
        )
        self.base_ang_vel[env_ids] = quat_rotate_inverse(
            self.base_quat[env_ids], self.root_states[env_ids, 10:13]
        )

    def _update_ref_root_pos_offsets(self, env_ids):
        samples = self.motion_loader.sample_by_time(self.motion_time_offsets[env_ids])
        root_pos = self.root_states[env_ids, :3] - self.env_origins[env_ids]
        offset = root_pos - samples["root_pos"]
        if not getattr(self.cfg.motion_reference, "align_ref_root_height_on_reset", True):
            offset[:, 2] = 0.0
        self.ref_root_pos_offset[env_ids] = offset

    def compute_ref_state(self):
        if self.motion_loader is not None:
            motion_cfg = self.cfg.motion_reference
            motion_times = (
                self.phase_length_buf.float() * self.dt * motion_cfg.playback_speed
                + self.motion_time_offsets
            )
            samples = self.motion_loader.sample_by_time(motion_times)
            self.ref_root_pos = samples["root_pos"]
            self.aligned_ref_root_pos = self.ref_root_pos + self.ref_root_pos_offset
            self.ref_root_quat = samples["root_quat"]
            self.ref_root_lin_vel = samples["root_lin_vel"]
            self.ref_root_ang_vel = samples["root_ang_vel"]
            self.ref_dof_pos = samples["dof_pos"]
            self.ref_dof_vel = samples["dof_vel"]
            self.ref_foot_contacts = samples.get("foot_contacts")
            self._update_ref_body_pos_diagnostics(samples)

            if motion_cfg.stand_uses_default_pose:
                stand_command = (
                    torch.norm(self.commands[:, :3], dim=1)
                    <= self.cfg.commands.stand_com_threshold
                )
                self.ref_dof_pos[stand_command] = self.default_dof_pos.expand_as(
                    self.ref_dof_pos[stand_command]
                )
                self.ref_dof_vel[stand_command] = 0.0
                self.ref_root_lin_vel[stand_command] = 0.0
                self.ref_root_ang_vel[stand_command] = 0.0

            ref_delta = self.ref_dof_pos - self.default_dof_pos
            action_scale = self.action_scale
            if not torch.is_tensor(action_scale):
                action_scale = torch.tensor(action_scale, device=self.device)
            self.ref_action = ref_delta / torch.clamp(action_scale, min=1e-6)
            return

        phase = self._get_phase()
        sin_pos = torch.sin(2 * torch.pi * phase)
        sin_pos_l = sin_pos.clone()
        sin_pos_r = sin_pos.clone()

        self.ref_dof_pos = torch.zeros_like(self.dof_pos)
        swing_delta = self.cfg.rewards.final_swing_joint_delta_pos
        left_leg_start = 0
        right_leg_start = 23

        sin_pos_l[sin_pos_l > 0] = 0
        for i in range(6):
            self.ref_dof_pos[:, left_leg_start + i] = -sin_pos_l * swing_delta[i]

        sin_pos_r[sin_pos_r < 0] = 0
        for i in range(6):
            self.ref_dof_pos[:, right_leg_start + i] = sin_pos_r * swing_delta[6 + i]

        self.ref_dof_pos[torch.abs(sin_pos) < 0.1] = 0.
        action_scale = self.action_scale
        if not torch.is_tensor(action_scale):
            action_scale = torch.tensor(action_scale, device=self.device)
        self.ref_action = self.ref_dof_pos / torch.clamp(action_scale, min=1e-6)
        self.ref_dof_pos += self.default_dof_pos

    def _update_ref_body_pos_diagnostics(self, samples):
        if (
            "body_pos" not in samples
            or not self.ref_body_pos_names
        ):
            self.ref_body_pos = None
            self.body_pos_world = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.aligned_ref_body_pos_world = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.body_pos_local = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.ref_body_pos_local = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.ref_body_pos_local_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.ref_body_pos_local_error = torch.zeros((self.num_envs, 0), device=self.device)
            self.ref_body_pos_world_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.ref_body_pos_world_error = torch.zeros((self.num_envs, 0), device=self.device)
            self.ref_body_pos_error_xyz = torch.zeros((self.num_envs, 0, 3), device=self.device)
            self.ref_body_pos_error = torch.zeros((self.num_envs, 0), device=self.device)
            self.ref_body_pos_error_mean.zero_()
            self.ref_body_pos_error_max.zero_()
            return

        ref_parts = []
        body_parts = []
        if self.ref_body_pos_motion_indices.numel() > 0:
            ref_parts.append(samples["body_pos"][:, self.ref_body_pos_motion_indices])
            body_parts.append(
                self.rigid_state[:, self.ref_body_pos_body_indices, :3]
                - self.env_origins[:, None, :]
            )
        if self.ref_virtual_body_pos_motion_indices.numel() > 0:
            ref_parts.append(samples["body_pos"][:, self.ref_virtual_body_pos_motion_indices])
            parent_pos = (
                self.rigid_state[:, self.ref_virtual_body_pos_parent_indices, :3]
                - self.env_origins[:, None, :]
            )
            parent_quat = self.rigid_state[:, self.ref_virtual_body_pos_parent_indices, 3:7]
            virtual_offsets = self.ref_virtual_body_pos_offsets.expand(self.num_envs, -1, -1)
            virtual_pos = parent_pos + quat_rotate(
                parent_quat.reshape(-1, 4),
                virtual_offsets.reshape(-1, 3),
            ).view(self.num_envs, -1, 3)
            body_parts.append(virtual_pos)
        ref_body_pos = torch.cat(ref_parts, dim=1)
        body_pos = torch.cat(body_parts, dim=1)
        root_pos = self.root_states[:, :3] - self.env_origins
        root_quat = self.root_states[:, 3:7]

        ref_root_pos = self.ref_root_pos
        ref_root_quat = self.ref_root_quat
        body_local = quat_rotate_inverse(
            root_quat[:, None, :].expand(-1, body_pos.shape[1], -1).reshape(-1, 4),
            (body_pos - root_pos[:, None, :]).reshape(-1, 3),
        ).view(self.num_envs, body_pos.shape[1], 3)
        ref_body_local = quat_rotate_inverse(
            ref_root_quat[:, None, :].expand(-1, ref_body_pos.shape[1], -1).reshape(-1, 4),
            (ref_body_pos - ref_root_pos[:, None, :]).reshape(-1, 3),
        ).view(self.num_envs, ref_body_pos.shape[1], 3)

        self.ref_body_pos = ref_body_pos
        self.body_pos_world = body_pos + self.env_origins[:, None, :]
        self.aligned_ref_body_pos_world = (
            ref_body_pos
            + self.ref_root_pos_offset[:, None, :]
            + self.env_origins[:, None, :]
        )
        self.body_pos_local = body_local
        self.ref_body_pos_local = ref_body_local
        self.ref_body_pos_local_error_xyz = body_local - ref_body_local
        self.ref_body_pos_local_error = torch.norm(self.ref_body_pos_local_error_xyz, dim=-1)
        self.ref_body_pos_world_error_xyz = self.body_pos_world - self.aligned_ref_body_pos_world
        self.ref_body_pos_world_error = torch.norm(self.ref_body_pos_world_error_xyz, dim=-1)
        # Backward-compatible diagnostic aliases. The keypoint reward below uses world error.
        self.ref_body_pos_error_xyz = self.ref_body_pos_local_error_xyz
        self.ref_body_pos_error = self.ref_body_pos_local_error
        self.ref_body_pos_error_mean = torch.mean(self.ref_body_pos_world_error, dim=1)
        self.ref_body_pos_error_max = torch.max(self.ref_body_pos_world_error, dim=1).values

    def check_termination(self):
        if self.motion_loader is not None:
            self.compute_ref_state()

        super().check_termination()

        xy_threshold = getattr(self.cfg.rewards, "termination_max_ref_root_xy_distance", None)
        xyz_threshold = getattr(self.cfg.rewards, "termination_max_ref_root_xyz_distance", None)
        joint_threshold = getattr(self.cfg.rewards, "termination_max_ref_joint_pos_error", None)
        joint_grace_steps = getattr(self.cfg.rewards, "termination_ref_joint_grace_steps", 0)
        support_rect_margin = getattr(self.cfg.rewards, "termination_support_rect_margin", None)
        world_keypoint_rules = getattr(self.cfg.rewards, "termination_world_keypoint_thresholds", ())
        root_pos = self.root_states[:, :3] - self.env_origins

        if self.motion_loader is None or xy_threshold is None:
            ref_root_xy_distance = torch.zeros(self.num_envs, device=self.device)
            ref_root_xy_cutoff = torch.zeros_like(self.reset_buf)
        else:
            ref_root_xy_distance = torch.norm(root_pos[:, :2] - self.aligned_ref_root_pos[:, :2], dim=1)
            ref_root_xy_cutoff = ref_root_xy_distance > xy_threshold

        if self.motion_loader is None or xyz_threshold is None:
            ref_root_xyz_distance = torch.zeros(self.num_envs, device=self.device)
            ref_root_xyz_cutoff = torch.zeros_like(self.reset_buf)
        else:
            ref_root_xyz_distance = torch.norm(root_pos - self.aligned_ref_root_pos, dim=1)
            ref_root_xyz_cutoff = ref_root_xyz_distance > xyz_threshold

        self.ref_root_xy_distance = ref_root_xy_distance
        self.ref_root_xyz_distance = ref_root_xyz_distance
        self.termination_ref_root_xy_buf = ref_root_xy_cutoff
        self.termination_ref_root_xyz_buf = ref_root_xyz_cutoff
        self.ref_joint_pos_error = torch.abs(self.dof_pos - self.ref_dof_pos)
        self.ref_joint_pos_error_max = torch.max(self.ref_joint_pos_error, dim=1).values

        if support_rect_margin is None or len(self.feet_indices) < 2:
            support_rect_distance = torch.zeros(self.num_envs, device=self.device)
            support_rect_cutoff = torch.zeros_like(self.reset_buf)
            com_xy = root_pos[:, :2]
        else:
            feet_xy = self.rigid_state[:, self.feet_indices, :2] - self.env_origins[:, None, :2]
            rect_min = torch.min(feet_xy, dim=1).values - support_rect_margin
            rect_max = torch.max(feet_xy, dim=1).values + support_rect_margin
            masses = self.rigid_body_masses
            total_mass = torch.clamp(torch.sum(masses, dim=1, keepdim=True), min=1e-6)
            body_quat = self.rigid_state[:, :, 3:7].reshape(-1, 4)
            local_com = self.rigid_body_com_offsets.reshape(-1, 3)
            world_com = self.rigid_state[:, :, :3] + quat_rotate(body_quat, local_com).view(
                self.num_envs, self.num_bodies, 3
            )
            com_xy = torch.sum(world_com[:, :, :2] * masses[:, :, None], dim=1) / total_mass
            com_xy = com_xy - self.env_origins[:, :2]
            outside_low = torch.clamp(rect_min - com_xy, min=0.0)
            outside_high = torch.clamp(com_xy - rect_max, min=0.0)
            support_rect_distance = torch.norm(outside_low + outside_high, dim=1)
            support_rect_cutoff = support_rect_distance > 0.0

        if self.motion_loader is None or joint_threshold is None:
            ref_joint_cutoff = torch.zeros_like(self.reset_buf)
        else:
            ref_joint_cutoff = self.ref_joint_pos_error_max > joint_threshold
            if joint_grace_steps > 0:
                ref_joint_cutoff &= self.episode_length_buf > joint_grace_steps

        world_keypoint_cutoff = torch.zeros_like(self.reset_buf)
        world_keypoint_error_max = torch.zeros(self.num_envs, device=self.device)
        if (
            self.motion_loader is not None
            and world_keypoint_rules
            and self.ref_body_pos_world_error.numel() > 0
            and self.ref_body_pos_names
        ):
            for label, tokens, threshold in world_keypoint_rules:
                indices = self._body_pos_indices_containing(tokens)
                if indices.numel() == 0:
                    continue
                rule_error_max = torch.max(self.ref_body_pos_world_error[:, indices], dim=1).values
                rule_cutoff = rule_error_max > threshold
                safe_label = str(label).replace("-", "_")
                setattr(self, f"termination_world_keypoint_{safe_label}_buf", rule_cutoff)
                setattr(self, f"world_keypoint_{safe_label}_error_max", rule_error_max)
                world_keypoint_cutoff |= rule_cutoff
                world_keypoint_error_max = torch.maximum(world_keypoint_error_max, rule_error_max)

        self.termination_ref_joint_pos_buf = ref_joint_cutoff
        self.com_xy_position = com_xy
        self.support_rect_outside_distance = support_rect_distance
        self.termination_support_rect_buf = support_rect_cutoff
        self.termination_world_keypoint_buf = world_keypoint_cutoff
        self.world_keypoint_termination_error_max = world_keypoint_error_max
        self.reset_buf |= ref_root_xy_cutoff
        self.reset_buf |= ref_root_xyz_cutoff
        self.reset_buf |= ref_joint_cutoff
        self.reset_buf |= support_rect_cutoff
        self.reset_buf |= world_keypoint_cutoff

    def _reward_ref_joint_pos(self):
        joint_pos = self.dof_pos.clone()
        pos_target = self.ref_dof_pos.clone()
        motion_cfg = getattr(self.cfg, "motion_reference", None)
        if motion_cfg is None or motion_cfg.stand_uses_default_pose:
            stand_command = (
                torch.norm(self.commands[:, :3], dim=1)
                <= self.cfg.commands.stand_com_threshold
            )
            pos_target[stand_command] = self.default_dof_pos.clone()
        diff = joint_pos - pos_target
        r = torch.exp(-2 * torch.norm(diff, dim=1)) - 0.2 * torch.norm(diff, dim=1).clamp(0, 0.5)
        if motion_cfg is None or motion_cfg.stand_uses_default_pose:
            r[stand_command] = 1.0
        return r

    def _dof_indices_containing(self, tokens):
        indices = [
            i for i, name in enumerate(self.dof_names)
            if any(token in name for token in tokens)
        ]
        return torch.tensor(indices, dtype=torch.long, device=self.device)

    def _body_pos_indices_containing(self, tokens):
        indices = [
            i for i, name in enumerate(self.ref_body_pos_names)
            if any(token in name for token in tokens)
        ]
        return torch.tensor(indices, dtype=torch.long, device=self.device)

    def _reward_ref_joint_subset_pos(self, tokens, sigma=2.0):
        indices = self._dof_indices_containing(tokens)
        if indices.numel() == 0:
            return torch.zeros(self.num_envs, device=self.device)
        diff = self.dof_pos[:, indices] - self.ref_dof_pos[:, indices]
        error = torch.norm(diff, dim=1)
        return torch.exp(-sigma * error) - 0.2 * error.clamp(0, 0.5)

    def _reward_ref_keypoint_pos(self):
        if self.ref_body_pos_world_error.numel() == 0 or not self.ref_body_pos_names:
            return torch.zeros(self.num_envs, device=self.device)
        tokens = getattr(self.cfg.rewards, "motion_keypoint_pos_tokens", ())
        indices = self._body_pos_indices_containing(tokens) if tokens else None
        if indices is not None:
            if indices.numel() == 0:
                return torch.zeros(self.num_envs, device=self.device)
            errors = self.ref_body_pos_world_error[:, indices]
        else:
            errors = self.ref_body_pos_world_error
        mean_error = torch.mean(errors, dim=1)
        max_error = torch.max(errors, dim=1).values
        sigma = getattr(self.cfg.rewards, "motion_keypoint_pos_sigma", 20.0)
        max_sigma = getattr(self.cfg.rewards, "motion_keypoint_max_pos_sigma", sigma)
        return torch.exp(-sigma * mean_error) * torch.exp(-max_sigma * max_error)

    def _reward_ref_keypoint_group_pos(self, tokens, sigma_attr):
        if self.ref_body_pos_world_error.numel() == 0 or not self.ref_body_pos_names:
            return torch.zeros(self.num_envs, device=self.device)
        indices = self._body_pos_indices_containing(tokens)
        if indices.numel() == 0:
            return torch.zeros(self.num_envs, device=self.device)
        error = torch.max(self.ref_body_pos_world_error[:, indices], dim=1).values
        sigma = getattr(self.cfg.rewards, sigma_attr, getattr(self.cfg.rewards, "motion_keypoint_pos_sigma", 20.0))
        return torch.exp(-sigma * error)

    def _reward_ref_keypoint_ankle_pos(self):
        return self._reward_ref_keypoint_group_pos(("ankle",), "motion_keypoint_ankle_sigma")

    def _reward_ref_keypoint_knee_pos(self):
        return self._reward_ref_keypoint_group_pos(("knee",), "motion_keypoint_knee_sigma")

    def _reward_ref_keypoint_hip_lumbar_pos(self):
        return self._reward_ref_keypoint_group_pos(("hip", "lumbar"), "motion_keypoint_hip_lumbar_sigma")

    def _reward_ref_keypoint_base_head_pos(self):
        return self._reward_ref_keypoint_group_pos(("base", "head", "neck"), "motion_keypoint_base_head_sigma")

    def _reward_ref_keypoint_upper_body_pos(self):
        return self._reward_ref_keypoint_group_pos(("shoulder", "elbow"), "motion_keypoint_upper_body_sigma")
    def _reward_ref_lower_body_pos(self):
        return self._reward_ref_joint_subset_pos(("hip", "knee", "ankle"))

    def _reward_ref_upper_body_pos(self):
        return self._reward_ref_joint_subset_pos(("shoulder", "elbow", "wrist"))

    def _reward_ref_lumbar_pos(self):
        return self._reward_ref_joint_subset_pos(("lumbar",))

    def _reward_default_joint_pos(self):
        joint_diff = self.dof_pos - self.default_joint_pd_target
        left_yaw_roll = joint_diff[:, [1, 2, 5]]
        right_yaw_roll = joint_diff[:, [24, 25, 28]]
        yaw_roll = torch.norm(left_yaw_roll, dim=1) + torch.norm(right_yaw_roll, dim=1)
        yaw_roll = torch.clamp(yaw_roll - 0.1, 0, 50)
        return torch.exp(-yaw_roll * 100) - 0.01 * torch.norm(joint_diff, dim=1)

    def _reward_tracking_motion_dof(self):
        if self.motion_loader is None:
            return torch.zeros(self.num_envs, device=self.device)
        diff = self.dof_pos - self.ref_dof_pos
        sigma = getattr(self.cfg.rewards, "tracking_motion_dof_sigma", 1.5)
        return torch.exp(-torch.sum(torch.square(diff), dim=1) / max(sigma * sigma, 1e-6))

    def _reward_tracking_motion_vel(self):
        if self.motion_loader is None:
            return torch.zeros(self.num_envs, device=self.device)
        error = self.root_states[:, 7:9] - self.ref_root_lin_vel[:, :2]
        sigma = getattr(self.cfg.rewards, "tracking_motion_vel_sigma", 1.0)
        return torch.exp(-torch.sum(torch.square(error), dim=1) / max(sigma * sigma, 1e-6))

    def _reward_alive(self):
        return torch.ones(self.num_envs, device=self.device)

    def _reward_action_smoothness(self):
        actions = getattr(self, "policy_actions", self.actions)
        last_actions = getattr(self, "last_policy_actions", self.last_actions)
        last_last_actions = getattr(self, "last_last_policy_actions", self.last_last_actions)
        term_1 = torch.sum(torch.square(last_actions - actions), dim=1)
        term_2 = torch.sum(torch.square(actions + last_last_actions - 2 * last_actions), dim=1)
        term_3 = 0.05 * torch.sum(torch.abs(actions), dim=1)
        return term_1 + term_2 + term_3

    def _reward_action_regularization(self):
        actions = getattr(self, "policy_actions", self.actions)
        return torch.sum(torch.square(actions), dim=1)

    def _reward_lin_vel_z(self):
        return torch.square(self.base_lin_vel[:, 2])

    def _reward_yaw_penalty(self):
        return torch.square(self.base_euler_xyz[:, 2])

    def _reward_motion_dof_vel(self):
        error = torch.norm(self.dof_vel - self.ref_dof_vel, dim=1)
        return torch.exp(-error * self.cfg.rewards.motion_dof_vel_sigma)

    def _reward_motion_lower_body_vel(self):
        indices = self._dof_indices_containing(("hip", "knee", "ankle"))
        if indices.numel() == 0:
            return torch.zeros(self.num_envs, device=self.device)
        error = torch.norm(self.dof_vel[:, indices] - self.ref_dof_vel[:, indices], dim=1)
        return torch.exp(-error * self.cfg.rewards.motion_dof_vel_sigma)

    def _reward_base_height_floor_error(self):
        root_height = self.root_states[:, 2] - self.env_origins[:, 2]
        floor = getattr(self.cfg.rewards, "base_height_floor", 0.56)
        return torch.square(torch.clamp(floor - root_height, min=0.0))

    def _reward_motion_root_height(self):
        root_height = self.root_states[:, 2] - self.env_origins[:, 2]
        target_height = self.aligned_ref_root_pos[:, 2]
        error = torch.abs(root_height - target_height)
        return torch.exp(-error * self.cfg.rewards.motion_root_height_sigma)

    def _reward_motion_root_height_error(self):
        root_height = self.root_states[:, 2] - self.env_origins[:, 2]
        target_height = self.aligned_ref_root_pos[:, 2]
        tolerance = getattr(self.cfg.rewards, "motion_root_height_error_tolerance", 0.03)
        low_error = torch.clamp(target_height - root_height - tolerance, min=0.0)
        return torch.square(low_error)

    def _reward_motion_root_orientation(self):
        quat_error = _quat_mul(self.base_quat, _quat_conjugate(self.ref_root_quat))
        quat_error = torch.nn.functional.normalize(quat_error, dim=-1)
        angle_error = 2.0 * torch.atan2(
            torch.norm(quat_error[:, :3], dim=1),
            torch.abs(quat_error[:, 3]).clamp(min=1e-6),
        )
        return torch.exp(-angle_error * self.cfg.rewards.motion_root_orientation_sigma)

    def _reward_motion_root_lin_vel(self):
        error = torch.norm(self.root_states[:, 7:10] - self.ref_root_lin_vel, dim=1)
        return torch.exp(-error * self.cfg.rewards.motion_root_lin_vel_sigma)

    def _reward_motion_root_ang_vel(self):
        error = torch.norm(self.root_states[:, 10:13] - self.ref_root_ang_vel, dim=1)
        return torch.exp(-error * self.cfg.rewards.motion_root_ang_vel_sigma)

    def _reward_motion_contact_schedule(self):
        if self.ref_foot_contacts is None:
            return torch.zeros(self.num_envs, device=self.device)
        contact = (self.contact_forces[:, self.feet_indices, 2] > 5.).float()
        target_contact = (self.ref_foot_contacts > 0.5).float()
        matches = (contact == target_contact).float()
        return torch.mean(matches, dim=1)
