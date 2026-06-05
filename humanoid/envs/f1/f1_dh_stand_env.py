# Copyright (c) 2024, AgiBot Inc. All rights reserved.

import torch

from humanoid.envs.x1.x1_dh_stand_env import X1DHStandEnv


class F1DHStandEnv(X1DHStandEnv):
    """F1 29-DOF variant of the X1 walking environment."""

    def compute_ref_state(self):
        phase = self._get_phase()
        sin_pos = torch.sin(2 * torch.pi * phase)
        sin_pos_l = sin_pos.clone()
        sin_pos_r = sin_pos.clone()

        self.ref_dof_pos = torch.zeros_like(self.dof_pos)
        swing_delta = self.cfg.rewards.final_swing_joint_delta_pos
        left_leg_start = 17
        right_leg_start = 23

        sin_pos_l[sin_pos_l > 0] = 0
        for i in range(6):
            self.ref_dof_pos[:, left_leg_start + i] = -sin_pos_l * swing_delta[i]

        sin_pos_r[sin_pos_r < 0] = 0
        for i in range(6):
            self.ref_dof_pos[:, right_leg_start + i] = sin_pos_r * swing_delta[6 + i]

        self.ref_dof_pos[torch.abs(sin_pos) < 0.1] = 0.
        self.ref_action = 2 * self.ref_dof_pos
        self.ref_dof_pos += self.default_dof_pos

    def _reward_default_joint_pos(self):
        joint_diff = self.dof_pos - self.default_joint_pd_target
        left_yaw_roll = joint_diff[:, [18, 19, 22]]
        right_yaw_roll = joint_diff[:, [24, 25, 28]]
        yaw_roll = torch.norm(left_yaw_roll, dim=1) + torch.norm(right_yaw_roll, dim=1)
        yaw_roll = torch.clamp(yaw_roll - 0.1, 0, 50)
        return torch.exp(-yaw_roll * 100) - 0.01 * torch.norm(joint_diff, dim=1)
