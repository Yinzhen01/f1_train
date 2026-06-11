# Copyright (c) 2024, AgiBot Inc. All rights reserved.

import torch
from isaacgym import gymtorch

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


class F1DHStandEnv(X1DHStandEnv):
    """F1 29-DOF variant of the X1 walking environment."""

    def _init_buffers(self):
        super()._init_buffers()
        self.motion_loader = None
        self.motion_time_offsets = torch.zeros(self.num_envs, device=self.device)
        self.ref_action = torch.zeros((self.num_envs, self.num_actions), device=self.device)
        self.ref_dof_vel = torch.zeros_like(self.dof_vel)
        self.ref_root_pos = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_root_quat = torch.zeros((self.num_envs, 4), device=self.device)
        self.ref_root_quat[:, 3] = 1.0
        self.ref_root_lin_vel = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_root_ang_vel = torch.zeros((self.num_envs, 3), device=self.device)
        self.ref_foot_contacts = None

        motion_cfg = getattr(self.cfg, "motion_reference", None)
        if motion_cfg is None or not motion_cfg.enabled:
            return

        self.motion_loader = MotionLoader(
            motion_cfg.file,
            device=self.device,
            expected_joint_names=self.dof_names,
        )
        if motion_cfg.randomize_start_phase:
            self.motion_time_offsets = torch.rand(self.num_envs, device=self.device) * self.motion_loader.duration

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
        if len(env_ids) > 0 and self.motion_loader is not None:
            motion_cfg = self.cfg.motion_reference
            if motion_cfg.randomize_start_phase:
                self.motion_time_offsets[env_ids] = (
                    torch.rand(len(env_ids), device=self.device) * self.motion_loader.duration
                )
            else:
                self.motion_time_offsets[env_ids] = 0.0
        return super().reset_idx(env_ids)

    def compute_ref_state(self):
        if self.motion_loader is not None:
            motion_cfg = self.cfg.motion_reference
            motion_times = (
                self.phase_length_buf.float() * self.dt * motion_cfg.playback_speed
                + self.motion_time_offsets
            )
            samples = self.motion_loader.sample_by_time(motion_times)
            self.ref_root_pos = samples["root_pos"]
            self.ref_root_quat = samples["root_quat"]
            self.ref_root_lin_vel = samples["root_lin_vel"]
            self.ref_root_ang_vel = samples["root_ang_vel"]
            self.ref_dof_pos = samples["dof_pos"]
            self.ref_dof_vel = samples["dof_vel"]
            self.ref_foot_contacts = samples.get("foot_contacts")

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

    def _reward_default_joint_pos(self):
        joint_diff = self.dof_pos - self.default_joint_pd_target
        left_yaw_roll = joint_diff[:, [1, 2, 5]]
        right_yaw_roll = joint_diff[:, [24, 25, 28]]
        yaw_roll = torch.norm(left_yaw_roll, dim=1) + torch.norm(right_yaw_roll, dim=1)
        yaw_roll = torch.clamp(yaw_roll - 0.1, 0, 50)
        return torch.exp(-yaw_roll * 100) - 0.01 * torch.norm(joint_diff, dim=1)

    def _reward_motion_dof_vel(self):
        error = torch.norm(self.dof_vel - self.ref_dof_vel, dim=1)
        return torch.exp(-error * self.cfg.rewards.motion_dof_vel_sigma)

    def _reward_motion_root_height(self):
        root_height = self.root_states[:, 2] - self.env_origins[:, 2]
        error = torch.abs(root_height - self.ref_root_pos[:, 2])
        return torch.exp(-error * self.cfg.rewards.motion_root_height_sigma)

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
