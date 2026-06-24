import os
from types import MethodType

from humanoid.envs import *  # noqa: F401,F403
from humanoid.utils import get_args, task_registry

import torch


def _parse_float_list(name, default):
    raw = os.environ.get(name, default)
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _disable_domain_randomization(cfg):
    for name in dir(cfg.domain_rand):
        if name.startswith("randomize_"):
            value = getattr(cfg.domain_rand, name)
            if isinstance(value, bool):
                setattr(cfg.domain_rand, name, False)
    for name in (
        "push_robots",
        "add_ext_force",
        "continuous_push",
        "add_lag",
        "add_dof_lag",
        "add_dof_pos_vel_lag",
        "add_imu_lag",
        "randomize_coulomb_friction",
    ):
        if hasattr(cfg.domain_rand, name):
            setattr(cfg.domain_rand, name, False)


def _install_nonresetting_termination(env):
    def check_termination_no_reset(self):
        if self.termination_contact_indices.numel() == 0:
            base_contact = torch.zeros(self.num_envs, dtype=torch.bool, device=self.device)
        else:
            base_contact = torch.any(
                torch.norm(self.contact_forces[:, self.termination_contact_indices, :], dim=-1) > 1.0,
                dim=1,
            )
        roll_cutoff = torch.abs(self.base_euler_xyz[:, 0]) > 1.5
        pitch_cutoff = torch.abs(self.base_euler_xyz[:, 1]) > 1.5
        min_base_height = getattr(self.cfg.rewards, "termination_min_base_height", None)
        if min_base_height is None:
            height_cutoff = torch.zeros_like(base_contact)
        else:
            base_height = self.root_states[:, 2] - self.env_origins[:, 2]
            height_cutoff = base_height < min_base_height

        self.termination_base_contact_buf = base_contact
        self.termination_roll_buf = roll_cutoff
        self.termination_pitch_buf = pitch_cutoff
        self.termination_height_buf = height_cutoff
        self.time_out_buf = torch.zeros_like(base_contact)
        self.reset_buf = torch.zeros_like(base_contact)

    env.check_termination = MethodType(check_termination_no_reset, env)


def _summarize(env, min_height, max_roll, max_pitch, max_dof_error, max_torque):
    root_height = env.root_states[:, 2] - env.env_origins[:, 2]
    dof_error = torch.mean(torch.abs(env.dof_pos - env.ref_dof_pos), dim=1)
    foot_force = env.contact_forces[:, env.feet_indices, 2]
    return {
        "final_h": root_height.mean().item(),
        "min_h": min_height.item(),
        "ref_h": env.aligned_ref_root_pos[:, 2].mean().item(),
        "roll_max": max_roll.item(),
        "pitch_max": max_pitch.item(),
        "dof_err": dof_error.mean().item(),
        "dof_err_max": max_dof_error.item(),
        "torque_max": max_torque.item(),
        "base_contact": env.termination_base_contact_buf.float().mean().item(),
        "height_cut": env.termination_height_buf.float().mean().item(),
        "foot_fz_l": foot_force[:, 0].mean().item(),
        "foot_fz_r": foot_force[:, 1].mean().item(),
    }


def main():
    args = get_args()
    task_name = os.environ.get("PD_HOLD_TASK", args.task)
    steps = int(os.environ.get("PD_HOLD_STEPS", "240"))
    num_envs = int(os.environ.get("PD_HOLD_NUM_ENVS", str(args.num_envs or 64)))
    offsets = _parse_float_list("PD_HOLD_OFFSETS", "0.0,0.05,0.1,0.15,0.2")
    gain_scales = _parse_float_list("PD_HOLD_GAIN_SCALES", "1.0,1.5,2.0,3.0")
    start_times = _parse_float_list("PD_HOLD_START_TIMES", "0.0")

    env_cfg, _ = task_registry.get_cfgs(task_name)
    env_cfg.env.num_envs = num_envs
    env_cfg.terrain.mesh_type = "plane"
    env_cfg.terrain.curriculum = False
    env_cfg.terrain.measure_heights = False
    env_cfg.noise.add_noise = False
    _disable_domain_randomization(env_cfg)
    env_cfg.motion_reference.randomize_start_phase = False
    env_cfg.motion_reference.start_time_offset = 0.0
    env_cfg.motion_reference.playback_speed = 0.0
    motion_file_override = os.environ.get("PD_HOLD_MOTION_FILE")
    if motion_file_override:
        env_cfg.motion_reference.file = motion_file_override
    env_cfg.rewards.termination_min_base_height = None
    env_cfg.rewards.termination_max_ref_root_xy_distance = None
    env_cfg.rewards.termination_max_ref_root_xyz_distance = None
    env_cfg.rewards.termination_max_ref_joint_pos_error = None
    env_cfg.rewards.termination_support_rect_margin = None
    env_cfg.rewards.termination_world_keypoint_thresholds = ()

    args.task = task_name
    args.num_envs = num_envs
    args.headless = True
    env, _ = task_registry.make_env(name=task_name, args=args, env_cfg=env_cfg)
    _install_nonresetting_termination(env)

    def compute_reward_noop(self):
        self.rew_buf[:] = 0.0

    env.compute_reward = MethodType(compute_reward_noop, env)

    base_p_gains = env.p_gains.clone()
    base_d_gains = env.d_gains.clone()
    zero_actions = torch.zeros(env.num_envs, env.num_actions, device=env.device)
    env_ids = torch.arange(env.num_envs, device=env.device)

    print(
        "task,num_envs,steps,start_time,offset,gain,final_h,min_h,ref_h,roll_max,pitch_max,"
        "dof_err,dof_err_max,torque_max,base_contact,height_cut,foot_fz_l,foot_fz_r"
    )

    for start_time in start_times:
        for offset in offsets:
            for gain in gain_scales:
                env.p_gains[:] = base_p_gains * gain
                env.d_gains[:] = base_d_gains * gain
                env.cfg.motion_reference.start_time_offset = start_time
                env.cfg.motion_reference.reset_root_height_offset = offset
                env.reset_idx(env_ids)
                env.compute_observations()

                min_height = torch.full((), float("inf"), device=env.device)
                max_roll = torch.zeros((), device=env.device)
                max_pitch = torch.zeros((), device=env.device)
                max_dof_error = torch.zeros((), device=env.device)
                max_torque = torch.zeros((), device=env.device)

                for _ in range(steps):
                    env.step(zero_actions)
                    root_height = env.root_states[:, 2] - env.env_origins[:, 2]
                    min_height = torch.minimum(min_height, root_height.min())
                    max_roll = torch.maximum(max_roll, torch.abs(env.base_euler_xyz[:, 0]).max())
                    max_pitch = torch.maximum(max_pitch, torch.abs(env.base_euler_xyz[:, 1]).max())
                    max_dof_error = torch.maximum(
                        max_dof_error,
                        torch.abs(env.dof_pos - env.ref_dof_pos).max(),
                    )
                    max_torque = torch.maximum(max_torque, torch.abs(env.torques).max())

                summary = _summarize(env, min_height, max_roll, max_pitch, max_dof_error, max_torque)
                print(
                    f"{task_name},{env.num_envs},{steps},{start_time:.4f},{offset:.3f},{gain:.2f},"
                    f"{summary['final_h']:.4f},{summary['min_h']:.4f},{summary['ref_h']:.4f},"
                    f"{summary['roll_max']:.4f},{summary['pitch_max']:.4f},"
                    f"{summary['dof_err']:.4f},{summary['dof_err_max']:.4f},"
                    f"{summary['torque_max']:.4f},{summary['base_contact']:.4f},"
                    f"{summary['height_cut']:.4f},{summary['foot_fz_l']:.2f},{summary['foot_fz_r']:.2f}"
                )


if __name__ == "__main__":
    main()
