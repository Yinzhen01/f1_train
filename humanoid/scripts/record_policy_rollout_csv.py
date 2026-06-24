# SPDX-License-Identifier: BSD-3-Clause

import csv
import os
from pathlib import Path

from isaacgym.torch_utils import *  # noqa: F401,F403

from humanoid import LEGGED_GYM_ROOT_DIR
from humanoid.envs import *  # noqa: F401,F403
from humanoid.utils import get_args, task_registry


def _disable_eval_randomness(env_cfg):
    env_cfg.terrain.mesh_type = "plane"
    env_cfg.terrain.num_rows = 1
    env_cfg.terrain.num_cols = 1
    env_cfg.terrain.max_init_terrain_level = 0
    env_cfg.noise.add_noise = False
    env_cfg.noise.curriculum = False
    env_cfg.commands.heading_command = False

    domain_rand = env_cfg.domain_rand
    for name in (
        "randomize_friction",
        "push_robots",
        "continuous_push",
        "randomize_base_mass",
        "randomize_com",
        "randomize_gains",
        "randomize_torque",
        "randomize_link_mass",
        "randomize_motor_offset",
        "randomize_joint_friction",
        "randomize_joint_damping",
        "randomize_joint_armature",
        "randomize_lag_timesteps",
    ):
        if hasattr(domain_rand, name):
            setattr(domain_rand, name, False)


def _row_from_env(env, step, dt, env_index=0):
    root = (env.root_states[env_index, :3] - env.env_origins[env_index]).detach().cpu().numpy()
    quat_xyzw = env.root_states[env_index, 3:7].detach().cpu().numpy()
    dof_pos = env.dof_pos[env_index].detach().cpu().numpy()
    return [
        step * dt,
        root[0],
        root[1],
        root[2],
        quat_xyzw[3],
        quat_xyzw[0],
        quat_xyzw[1],
        quat_xyzw[2],
        *dof_pos.tolist(),
    ]


def _set_fixed_command(env):
    if not hasattr(env, "commands"):
        return
    command = [
        float(os.environ.get("ROLLOUT_COMMAND_X", "0.0")),
        float(os.environ.get("ROLLOUT_COMMAND_Y", "0.0")),
        float(os.environ.get("ROLLOUT_COMMAND_YAW", "0.0")),
        float(os.environ.get("ROLLOUT_COMMAND_HEADING", "0.0")),
    ]
    for idx, value in enumerate(command[: env.commands.shape[1]]):
        env.commands[:, idx] = value

def record(args):
    steps = int(os.environ.get("ROLLOUT_STEPS", "1000"))
    output = Path(
        os.environ.get(
            "ROLLOUT_OUTPUT",
            os.path.join(LEGGED_GYM_ROOT_DIR, "videos", "policy_rollout.csv"),
        )
    )
    env_index = int(os.environ.get("ROLLOUT_ENV_INDEX", "0"))

    env_cfg, train_cfg = task_registry.get_cfgs(name=args.task)
    env_cfg.env.num_envs = min(env_cfg.env.num_envs, args.num_envs or 1)
    env_cfg.env.episode_length_s = max(getattr(env_cfg.env, "episode_length_s", 0), 1000)
    _disable_eval_randomness(env_cfg)

    train_cfg.runner.resume = True
    env, _ = task_registry.make_env(name=args.task, args=args, env_cfg=env_cfg)
    ppo_runner, train_cfg, _ = task_registry.make_alg_runner(
        env=env,
        name=args.task,
        args=args,
        train_cfg=train_cfg,
    )
    policy = ppo_runner.get_inference_policy(device=env.device)

    dt = env_cfg.sim.dt * env_cfg.control.decimation
    header = [
        "timestamp",
        "root_pos_x",
        "root_pos_y",
        "root_pos_z",
        "root_quat_w",
        "root_quat_x",
        "root_quat_y",
        "root_quat_z",
        *env.dof_names,
    ]

    output.parent.mkdir(parents=True, exist_ok=True)
    _set_fixed_command(env)
    obs = env.get_observations()
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(_row_from_env(env, 0, dt, env_index))
        for step in range(1, steps + 1):
            actions = policy(obs.detach())
            _set_fixed_command(env)
            obs, _, _, _, _ = env.step(actions.detach())
            _set_fixed_command(env)
            writer.writerow(_row_from_env(env, step, dt, env_index))

    print(f"wrote {output} ({steps + 1} frames, dt={dt:.4f}s)")
    print("joint columns:", ",".join(env.dof_names))


if __name__ == "__main__":
    record(get_args())



