# Copyright (c) 2024, AgiBot Inc. All rights reserved.

"""Train with an Isaac Gym viewer camera focused on one environment.

This script is intended for GUI cloud-desktop inspection. It keeps the normal
training path, then moves the viewer camera after the environment origins are
known, which is necessary on terrain where env 0 is not near world origin.
"""

import os

from humanoid.envs import *  # noqa: F401,F403
from humanoid.utils import get_args, task_registry

import torch


def _parse_vec(name, default):
    raw = os.environ.get(name, default)
    values = [float(x.strip()) for x in raw.split(",")]
    if len(values) != 3:
        raise ValueError(f"{name} must contain 3 comma-separated values, got: {raw}")
    return values


def _parse_bool(name):
    raw = os.environ.get(name)
    if raw is None:
        return None
    if raw.lower() in ("1", "true", "yes", "on"):
        return True
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name} must be true/false, got: {raw}")


def _reward_scale(cfg, name):
    return getattr(cfg.rewards.scales, name, None)


def _as_vector(value, length):
    if torch.is_tensor(value):
        return value.detach().flatten()
    return torch.full((length,), float(value))


def _joint_group(name):
    for group in ("hip", "knee", "ankle", "lumbar", "shoulder", "elbow", "wrist"):
        if f"_{group}_" in name:
            return group
    return "other"


def _set_if_present(obj, name, value):
    if hasattr(obj, name):
        setattr(obj, name, value)


def _disable_domain_randomization(domain_rand):
    bool_fields = (
        "randomize_friction",
        "push_robots",
        "randomize_base_mass",
        "randomize_com",
        "randomize_link_mass",
        "randomize_link_com",
        "randomize_base_inertia",
        "randomize_link_inertia",
        "randomize_gains",
        "randomize_torque",
        "randomize_motor_offset",
        "randomize_joint_friction",
        "randomize_joint_damping",
        "randomize_joint_armature",
        "randomize_coulomb_friction",
        "add_lag",
        "add_dof_lag",
        "add_dof_pos_vel_lag",
        "add_imu_lag",
        "add_ext_force",
    )
    for name in bool_fields:
        _set_if_present(domain_rand, name, False)


def _print_domain_randomization_context(domain_rand):
    for name in (
        "randomize_friction",
        "push_robots",
        "randomize_base_mass",
        "randomize_com",
        "randomize_link_mass",
        "randomize_gains",
        "randomize_torque",
        "randomize_motor_offset",
        "randomize_joint_friction",
        "randomize_joint_damping",
        "randomize_joint_armature",
        "randomize_coulomb_friction",
        "add_lag",
        "add_dof_lag",
        "add_dof_pos_vel_lag",
        "add_imu_lag",
        "add_ext_force",
    ):
        print(f"domain_rand.{name}: {getattr(domain_rand, name, None)}", flush=True)


def _print_training_context(args, env_cfg):
    motion_cfg = getattr(env_cfg, "motion_reference", None)
    print("task:", args.task, flush=True)
    print("asset:", env_cfg.asset.file, flush=True)
    print("asset.foot_name:", env_cfg.asset.foot_name, flush=True)
    print("terrain.mesh_type:", env_cfg.terrain.mesh_type, flush=True)
    print("terrain.curriculum:", env_cfg.terrain.curriculum, flush=True)
    print("terrain.max_init_terrain_level:", getattr(env_cfg.terrain, "max_init_terrain_level", None), flush=True)
    print("terrain.static_friction:", env_cfg.terrain.static_friction, flush=True)
    print("terrain.dynamic_friction:", env_cfg.terrain.dynamic_friction, flush=True)
    print("domain_rand.randomize_friction:", env_cfg.domain_rand.randomize_friction, flush=True)
    print("domain_rand.friction_range:", env_cfg.domain_rand.friction_range, flush=True)
    _print_domain_randomization_context(env_cfg.domain_rand)
    print(
        "rewards.termination_min_base_height:",
        getattr(env_cfg.rewards, "termination_min_base_height", None),
        flush=True,
    )
    print(
        "rewards.termination_max_ref_root_xy_distance:",
        getattr(env_cfg.rewards, "termination_max_ref_root_xy_distance", None),
        flush=True,
    )
    print(
        "rewards.termination_max_ref_root_xyz_distance:",
        getattr(env_cfg.rewards, "termination_max_ref_root_xyz_distance", None),
        flush=True,
    )
    print(
        "rewards.termination_max_ref_joint_pos_error:",
        getattr(env_cfg.rewards, "termination_max_ref_joint_pos_error", None),
        flush=True,
    )
    print(
        "rewards.termination_ref_joint_grace_steps:",
        getattr(env_cfg.rewards, "termination_ref_joint_grace_steps", None),
        flush=True,
    )
    print(
        "rewards.termination_support_rect_margin:",
        getattr(env_cfg.rewards, "termination_support_rect_margin", None),
        flush=True,
    )
    print("num_actions:", env_cfg.env.num_actions, flush=True)
    if motion_cfg is not None:
        print("motion_reference.enabled:", motion_cfg.enabled, flush=True)
        print("motion_reference.file:", motion_cfg.file, flush=True)
        print("motion_reference.stand_uses_default_pose:", motion_cfg.stand_uses_default_pose, flush=True)
        print("motion_reference.reset_root_orientation:", motion_cfg.reset_root_orientation, flush=True)
        print("motion_reference.reset_root_velocity:", motion_cfg.reset_root_velocity, flush=True)
        print(
            "motion_reference.reset_root_height_offset:",
            getattr(motion_cfg, "reset_root_height_offset", None),
            flush=True,
        )
        print("motion_reference.randomize_start_phase:", motion_cfg.randomize_start_phase, flush=True)
    print("env.use_ref_actions:", getattr(env_cfg.env, "use_ref_actions", None), flush=True)
    for name in (
        "ref_joint_pos",
        "ref_lower_body_pos",
        "ref_lumbar_pos",
        "ref_upper_body_pos",
        "motion_dof_vel",
        "motion_lower_body_vel",
        "motion_root_height",
        "motion_root_orientation",
        "motion_root_lin_vel",
        "motion_root_ang_vel",
        "tracking_lin_vel",
        "track_vel_hard",
        "feet_contact_number",
    ):
        print(f"reward_scale.{name}: {_reward_scale(env_cfg, name)}", flush=True)


def _print_training_hparams(train_cfg):
    print("policy.init_noise_std:", train_cfg.policy.init_noise_std, flush=True)
    print("algorithm.learning_rate:", train_cfg.algorithm.learning_rate, flush=True)
    print("algorithm.entropy_coef:", train_cfg.algorithm.entropy_coef, flush=True)
    print("algorithm.num_learning_epochs:", train_cfg.algorithm.num_learning_epochs, flush=True)
    print("algorithm.num_mini_batches:", train_cfg.algorithm.num_mini_batches, flush=True)
    print("runner.num_steps_per_env:", train_cfg.runner.num_steps_per_env, flush=True)


def _print_joint_reference_table(env, focus_env):
    if not hasattr(env, "ref_dof_pos"):
        return

    with torch.no_grad():
        env.compute_ref_state()
        action_scale = _as_vector(env.action_scale, env.num_actions).to(env.device)
        default = env.default_dof_pos[0]
        ref = env.ref_dof_pos[focus_env]
        ref_delta = ref - default
        ref_action = ref_delta / torch.clamp(action_scale, min=1e-6)

        print("joint_reference_table_begin", flush=True)
        print(
            "joint_reference_columns: idx name group action_scale default ref_pos ref_delta ref_action",
            flush=True,
        )
        for idx, name in enumerate(env.dof_names):
            print(
                "joint_reference:"
                f" {idx} {name} {_joint_group(name)}"
                f" {float(action_scale[idx]):.6f}"
                f" {float(default[idx]):.6f}"
                f" {float(ref[idx]):.6f}"
                f" {float(ref_delta[idx]):.6f}"
                f" {float(ref_action[idx]):.6f}",
                flush=True,
            )
        print("joint_reference_table_end", flush=True)


def _print_joint_error_diagnostics(env, topk, step, focus_env, print_all):
    if not hasattr(env, "ref_dof_pos") or not hasattr(env, "ref_dof_vel"):
        return

    with torch.no_grad():
        pos_err = torch.abs(env.dof_pos - env.ref_dof_pos).mean(dim=0)
        vel_err = torch.abs(env.dof_vel - env.ref_dof_vel).mean(dim=0)
        ref_delta = torch.abs(env.ref_dof_pos - env.default_dof_pos).mean(dim=0)
        mean_pos = env.dof_pos.mean(dim=0)
        mean_ref_pos = env.ref_dof_pos.mean(dim=0)
        focus_pos = env.dof_pos[focus_env]
        focus_ref_pos = env.ref_dof_pos[focus_env]
        focus_pos_err = torch.abs(focus_pos - focus_ref_pos)
        top_count = min(topk, env.num_actions)
        _, top_indices = torch.topk(pos_err, k=top_count)

        print(f"joint_diag_step: {step}", flush=True)
        print(
            "joint_diag_columns: idx name group mean_abs_pos_err mean_abs_vel_err mean_abs_ref_delta",
            flush=True,
        )
        for idx_t in top_indices:
            idx = int(idx_t)
            name = env.dof_names[idx]
            print(
                "joint_diag_top:"
                f" {idx} {name} {_joint_group(name)}"
                f" {float(pos_err[idx]):.6f}"
                f" {float(vel_err[idx]):.6f}"
                f" {float(ref_delta[idx]):.6f}",
                flush=True,
            )

        if print_all:
            print(
                "joint_diag_all_columns:"
                " idx name group mean_pos mean_ref_pos mean_abs_pos_err"
                " focus_pos focus_ref_pos focus_abs_pos_err mean_abs_vel_err mean_abs_ref_delta",
                flush=True,
            )
            for idx, name in enumerate(env.dof_names):
                print(
                    "joint_diag_all:"
                    f" {idx} {name} {_joint_group(name)}"
                    f" {float(mean_pos[idx]):.6f}"
                    f" {float(mean_ref_pos[idx]):.6f}"
                    f" {float(pos_err[idx]):.6f}"
                    f" {float(focus_pos[idx]):.6f}"
                    f" {float(focus_ref_pos[idx]):.6f}"
                    f" {float(focus_pos_err[idx]):.6f}"
                    f" {float(vel_err[idx]):.6f}"
                    f" {float(ref_delta[idx]):.6f}",
                    flush=True,
                )

        groups = {}
        for idx, name in enumerate(env.dof_names):
            groups.setdefault(_joint_group(name), []).append(idx)
        for group, indices in sorted(groups.items()):
            index_tensor = torch.tensor(indices, device=env.device)
            print(
                "joint_diag_group:"
                f" {group}"
                f" {float(pos_err[index_tensor].mean()):.6f}"
                f" {float(vel_err[index_tensor].mean()):.6f}"
                f" {float(ref_delta[index_tensor].mean()):.6f}",
                flush=True,
            )


def _install_joint_diagnostics(env):
    interval = int(os.environ.get("JOINT_DIAG_INTERVAL", "0"))
    if interval <= 0:
        return

    topk = int(os.environ.get("JOINT_DIAG_TOPK", "10"))
    focus_env = int(os.environ.get("VIEWER_FOCUS_ENV", "0"))
    print_all = _parse_bool("JOINT_DIAG_PRINT_ALL")
    print_all = bool(print_all) if print_all is not None else False
    if "ref_joint_pos" not in getattr(env, "reward_names", []):
        print("joint_diag: ref_joint_pos reward is not active", flush=True)
        return

    original_reward = env._reward_ref_joint_pos
    last_printed = {"step": -1}

    def reward_with_joint_diag():
        reward = original_reward()
        step = int(getattr(env, "common_step_counter", 0))
        if step > 0 and step % interval == 0 and step != last_printed["step"]:
            _print_joint_error_diagnostics(
                env,
                topk=topk,
                step=step,
                focus_env=focus_env,
                print_all=print_all,
            )
            last_printed["step"] = step
        return reward

    env._reward_ref_joint_pos = reward_with_joint_diag
    for idx, name in enumerate(env.reward_names):
        if name == "ref_joint_pos":
            env.reward_functions[idx] = reward_with_joint_diag
            break
    print(
        f"joint_diag.enabled: interval={interval} topk={topk} print_all={print_all}",
        flush=True,
    )


def _install_termination_diagnostics(env):
    interval = int(os.environ.get("TERMINATION_DIAG_INTERVAL", "0"))
    if interval <= 0:
        return

    original_check_termination = env.check_termination
    last_printed = {"step": -1}

    def _sum_bool_attr(name):
        value = getattr(env, name, None)
        if value is None:
            return 0
        return int(value.sum().item())

    def _stats_attr(name):
        value = getattr(env, name, None)
        if value is None:
            return 0.0, 0.0, 0.0
        return float(value.min()), float(value.mean()), float(value.max())

    def check_termination_with_diag():
        original_check_termination()
        step = int(getattr(env, "common_step_counter", 0))
        if step > 0 and step % interval == 0 and step != last_printed["step"]:
            base_height = env.root_states[:, 2] - env.env_origins[:, 2]
            ref_xy_min, ref_xy_mean, ref_xy_max = _stats_attr("ref_root_xy_distance")
            ref_xyz_min, ref_xyz_mean, ref_xyz_max = _stats_attr("ref_root_xyz_distance")
            ref_joint_min, ref_joint_mean, ref_joint_max = _stats_attr("ref_joint_pos_error_max")
            support_min, support_mean, support_max = _stats_attr("support_rect_outside_distance")
            print(f"termination_diag_step: {step}", flush=True)
            print(
                "termination_diag:"
                f" base_contact={_sum_bool_attr('termination_base_contact_buf')}"
                f" roll={_sum_bool_attr('termination_roll_buf')}"
                f" pitch={_sum_bool_attr('termination_pitch_buf')}"
                f" height={_sum_bool_attr('termination_height_buf')}"
                f" ref_xy={_sum_bool_attr('termination_ref_root_xy_buf')}"
                f" ref_xyz={_sum_bool_attr('termination_ref_root_xyz_buf')}"
                f" ref_joint={_sum_bool_attr('termination_ref_joint_pos_buf')}"
                f" support_rect={_sum_bool_attr('termination_support_rect_buf')}"
                f" timeout={int(env.time_out_buf.sum().item())}"
                f" reset_total={int(env.reset_buf.sum().item())}"
                f" base_height_min={float(base_height.min()):.6f}"
                f" base_height_mean={float(base_height.mean()):.6f}"
                f" base_height_max={float(base_height.max()):.6f}"
                f" ref_xy_dist_min={ref_xy_min:.6f}"
                f" ref_xy_dist_mean={ref_xy_mean:.6f}"
                f" ref_xy_dist_max={ref_xy_max:.6f}"
                f" ref_xyz_dist_min={ref_xyz_min:.6f}"
                f" ref_xyz_dist_mean={ref_xyz_mean:.6f}"
                f" ref_xyz_dist_max={ref_xyz_max:.6f}"
                f" ref_joint_err_min={ref_joint_min:.6f}"
                f" ref_joint_err_mean={ref_joint_mean:.6f}"
                f" ref_joint_err_max={ref_joint_max:.6f}"
                f" support_rect_outside_min={support_min:.6f}"
                f" support_rect_outside_mean={support_mean:.6f}"
                f" support_rect_outside_max={support_max:.6f}",
                flush=True,
            )
            last_printed["step"] = step

    env.check_termination = check_termination_with_diag
    print(f"termination_diag.enabled: interval={interval}", flush=True)


def _install_initial_settle_diagnostics(env):
    steps = int(os.environ.get("INITIAL_SETTLE_DIAG_STEPS", "0"))
    if steps <= 0:
        return

    focus_env = int(os.environ.get("INITIAL_SETTLE_DIAG_ENV", os.environ.get("VIEWER_FOCUS_ENV", "0")))
    if focus_env < 0 or focus_env >= env.num_envs:
        raise ValueError(f"INITIAL_SETTLE_DIAG_ENV={focus_env} is outside num_envs={env.num_envs}")

    original_step = env.step
    last_printed = {"step": -1}
    baseline = {"base_height": None}

    print(
        "initial_settle_diag.enabled:"
        f" steps={steps}"
        f" focus_env={focus_env}",
        flush=True,
    )

    def step_with_initial_settle_diag(actions):
        if baseline["base_height"] is None:
            baseline["base_height"] = (env.root_states[:, 2] - env.env_origins[:, 2]).clone()
            print(
                "initial_settle_diag_pre_step:"
                f" focus_base_height={float(baseline['base_height'][focus_env]):.6f}",
                flush=True,
            )
        result = original_step(actions)
        step = int(getattr(env, "common_step_counter", 0))
        if 0 < step <= steps and step != last_printed["step"]:
            base_height = env.root_states[:, 2] - env.env_origins[:, 2]
            foot_z = env.rigid_state[:, env.feet_indices, 2]
            contact = env.contact_forces[:, env.feet_indices, 2] > 5.0
            focus_base_height = base_height[focus_env]
            focus_delta = focus_base_height - baseline["base_height"][focus_env]
            focus_foot_z = foot_z[focus_env]
            focus_contact = contact[focus_env]
            print(
                "initial_settle_diag:"
                f" step={step}"
                f" focus_base_height={float(focus_base_height):.6f}"
                f" focus_base_delta={float(focus_delta):.6f}"
                f" focus_root_lin_vel_z={float(env.root_states[focus_env, 9]):.6f}"
                f" focus_foot_z_min={float(focus_foot_z.min()):.6f}"
                f" focus_foot_z_mean={float(focus_foot_z.mean()):.6f}"
                f" focus_contact_count={int(focus_contact.sum().item())}"
                f" base_height_min={float(base_height.min()):.6f}"
                f" base_height_mean={float(base_height.mean()):.6f}"
                f" base_delta_min={float((base_height - baseline['base_height']).min()):.6f}"
                f" base_delta_mean={float((base_height - baseline['base_height']).mean()):.6f}",
                flush=True,
            )
            last_printed["step"] = step
        return result

    env.step = step_with_initial_settle_diag


def train(args):
    env_cfg, train_cfg = task_registry.get_cfgs(name=args.task)
    domain_randomize_all = _parse_bool("DOMAIN_RANDOMIZE_ALL")
    if domain_randomize_all is False:
        _disable_domain_randomization(env_cfg.domain_rand)
    terrain_mesh_type = os.environ.get("TERRAIN_MESH_TYPE")
    if terrain_mesh_type:
        env_cfg.terrain.mesh_type = terrain_mesh_type
    terrain_static_friction = os.environ.get("TERRAIN_STATIC_FRICTION")
    if terrain_static_friction:
        env_cfg.terrain.static_friction = float(terrain_static_friction)
    terrain_dynamic_friction = os.environ.get("TERRAIN_DYNAMIC_FRICTION")
    if terrain_dynamic_friction:
        env_cfg.terrain.dynamic_friction = float(terrain_dynamic_friction)
    domain_randomize_friction = _parse_bool("DOMAIN_RANDOMIZE_FRICTION")
    if domain_randomize_friction is not None:
        env_cfg.domain_rand.randomize_friction = domain_randomize_friction
    motion_randomize_start_phase = _parse_bool("MOTION_RANDOMIZE_START_PHASE")
    motion_cfg = getattr(env_cfg, "motion_reference", None)
    if motion_cfg is not None and motion_randomize_start_phase is not None:
        motion_cfg.randomize_start_phase = motion_randomize_start_phase
    policy_init_noise_std = os.environ.get("POLICY_INIT_NOISE_STD")
    if policy_init_noise_std:
        train_cfg.policy.init_noise_std = float(policy_init_noise_std)
    ppo_learning_rate = os.environ.get("PPO_LEARNING_RATE")
    if ppo_learning_rate:
        train_cfg.algorithm.learning_rate = float(ppo_learning_rate)
    ppo_entropy_coef = os.environ.get("PPO_ENTROPY_COEF")
    if ppo_entropy_coef:
        train_cfg.algorithm.entropy_coef = float(ppo_entropy_coef)
    ppo_num_learning_epochs = os.environ.get("PPO_NUM_LEARNING_EPOCHS")
    if ppo_num_learning_epochs:
        train_cfg.algorithm.num_learning_epochs = int(ppo_num_learning_epochs)
    ppo_num_mini_batches = os.environ.get("PPO_NUM_MINI_BATCHES")
    if ppo_num_mini_batches:
        train_cfg.algorithm.num_mini_batches = int(ppo_num_mini_batches)
    ppo_num_steps_per_env = os.environ.get("PPO_NUM_STEPS_PER_ENV")
    if ppo_num_steps_per_env:
        train_cfg.runner.num_steps_per_env = int(ppo_num_steps_per_env)
    termination_min_base_height = os.environ.get("TERMINATION_MIN_BASE_HEIGHT")
    if termination_min_base_height:
        env_cfg.rewards.termination_min_base_height = float(termination_min_base_height)
    termination_max_ref_root_xy_distance = os.environ.get("TERMINATION_MAX_REF_ROOT_XY_DISTANCE")
    if termination_max_ref_root_xy_distance:
        env_cfg.rewards.termination_max_ref_root_xy_distance = float(termination_max_ref_root_xy_distance)
    termination_max_ref_root_xyz_distance = os.environ.get("TERMINATION_MAX_REF_ROOT_XYZ_DISTANCE")
    if termination_max_ref_root_xyz_distance:
        env_cfg.rewards.termination_max_ref_root_xyz_distance = float(termination_max_ref_root_xyz_distance)
    termination_max_ref_joint_pos_error = os.environ.get("TERMINATION_MAX_REF_JOINT_POS_ERROR")
    if termination_max_ref_joint_pos_error:
        env_cfg.rewards.termination_max_ref_joint_pos_error = float(termination_max_ref_joint_pos_error)
    termination_ref_joint_grace_steps = os.environ.get("TERMINATION_REF_JOINT_GRACE_STEPS")
    if termination_ref_joint_grace_steps is not None:
        env_cfg.rewards.termination_ref_joint_grace_steps = int(termination_ref_joint_grace_steps)
    termination_support_rect_margin = os.environ.get("TERMINATION_SUPPORT_RECT_MARGIN")
    if termination_support_rect_margin is not None:
        env_cfg.rewards.termination_support_rect_margin = float(termination_support_rect_margin)

    env, env_cfg = task_registry.make_env(name=args.task, args=args, env_cfg=env_cfg)
    _print_training_context(args, env_cfg)
    _print_training_hparams(train_cfg)

    focus_env = int(os.environ.get("VIEWER_FOCUS_ENV", "0"))
    rel_pos = _parse_vec("VIEWER_REL_POS", "1.3,-1.2,1.1")
    rel_lookat = _parse_vec("VIEWER_REL_LOOKAT", "0,0,0.75")

    if not env.headless and env.viewer is not None:
        if focus_env < 0 or focus_env >= env.num_envs:
            raise ValueError(f"VIEWER_FOCUS_ENV={focus_env} is outside num_envs={env.num_envs}")
        origin = env.env_origins[focus_env].detach().cpu().numpy().tolist()
        cam_pos = [origin[i] + rel_pos[i] for i in range(3)]
        cam_lookat = [origin[i] + rel_lookat[i] for i in range(3)]

        print("viewer.focus_env:", focus_env, flush=True)
        print("viewer.env_origin:", origin, flush=True)
        print("viewer.rel_pos:", rel_pos, flush=True)
        print("viewer.rel_lookat:", rel_lookat, flush=True)
        print("viewer.pos:", cam_pos, flush=True)
        print("viewer.lookat:", cam_lookat, flush=True)
        env.set_camera(cam_pos, cam_lookat)

    _print_joint_reference_table(env, focus_env)
    _install_joint_diagnostics(env)
    _install_termination_diagnostics(env)
    _install_initial_settle_diagnostics(env)

    ppo_runner, train_cfg, _ = task_registry.make_alg_runner(env=env, name=args.task, args=args, train_cfg=train_cfg)
    ppo_runner.learn(num_learning_iterations=train_cfg.runner.max_iterations, init_at_random_ep_len=False)


if __name__ == "__main__":
    train(get_args())
