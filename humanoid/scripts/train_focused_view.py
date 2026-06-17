# Copyright (c) 2024, AgiBot Inc. All rights reserved.

"""Train with an Isaac Gym viewer camera focused on one environment.

This script is intended for GUI cloud-desktop inspection. It keeps the normal
training path, then moves the viewer camera after the environment origins are
known, which is necessary on terrain where env 0 is not near world origin.
"""

import os

from isaacgym import gymapi, gymutil
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


def _parse_optional_float(raw):
    if raw is None:
        return None
    if raw.strip().lower() in ("", "none", "null", "off", "false", "disabled"):
        return None
    return float(raw)


def _parse_name_list(name):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _reward_scale(cfg, name):
    return getattr(cfg.rewards.scales, name, None)


def _as_vector(value, length):
    if torch.is_tensor(value):
        return value.detach().flatten()
    return torch.full((length,), float(value))


def _joint_group(name):
    for group in (
        "neck",
        "head",
        "base",
        "waist",
        "lumbar",
        "shoulder",
        "elbow",
        "wrist",
        "hip",
        "knee",
        "ankle",
        "toe",
        "arm",
        "leg",
    ):
        if f"_{group}_" in name:
            return group
        if name.startswith(f"{group}_"):
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
    print(
        "rewards.motion_keypoint_pos_sigma:",
        getattr(env_cfg.rewards, "motion_keypoint_pos_sigma", None),
        flush=True,
    )
    print(
        "rewards.motion_keypoint_pos_tokens:",
        getattr(env_cfg.rewards, "motion_keypoint_pos_tokens", None),
        flush=True,
    )
    print(
        "rewards.termination_world_keypoint_thresholds:",
        getattr(env_cfg.rewards, "termination_world_keypoint_thresholds", None),
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
        "ref_keypoint_pos",
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


def _print_body_pos_error_diagnostics(env, topk, step, focus_env, print_all):
    names = getattr(env, "ref_body_pos_names", [])
    errors = getattr(env, "ref_body_pos_world_error", None)
    if errors is None:
        errors = getattr(env, "ref_body_pos_error", None)
    if errors is None or errors.numel() == 0 or not names:
        print(f"body_pos_diag_step: {step}", flush=True)
        print(
            "body_pos_diag_unavailable: motion_body_pos=false matched_bodies=0",
            flush=True,
        )
        return

    with torch.no_grad():
        mean_err = errors.mean(dim=0)
        focus_err = errors[focus_env]
        top_count = min(topk, len(names))
        _, top_indices = torch.topk(mean_err, k=top_count)
        print(f"body_pos_diag_step: {step}", flush=True)
        print(
            "body_pos_diag_columns: idx name group mean_world_pos_err_m focus_world_pos_err_m",
            flush=True,
        )
        for idx_t in top_indices:
            idx = int(idx_t)
            name = names[idx]
            print(
                "body_pos_diag_top:"
                f" {idx} {name} {_joint_group(name)}"
                f" {float(mean_err[idx]):.6f}"
                f" {float(focus_err[idx]):.6f}",
                flush=True,
            )

        if print_all:
            print(
                "body_pos_diag_all_columns: idx name group mean_world_pos_err_m focus_world_pos_err_m",
                flush=True,
            )
            for idx, name in enumerate(names):
                print(
                    "body_pos_diag_all:"
                    f" {idx} {name} {_joint_group(name)}"
                    f" {float(mean_err[idx]):.6f}"
                    f" {float(focus_err[idx]):.6f}",
                    flush=True,
                )

        groups = {}
        for idx, name in enumerate(names):
            groups.setdefault(_joint_group(name), []).append(idx)
        for group, indices in sorted(groups.items()):
            index_tensor = torch.tensor(indices, device=env.device)
            print(
                "body_pos_diag_group:"
                f" {group}"
                f" {float(mean_err[index_tensor].mean()):.6f}"
                f" {float(focus_err[index_tensor].mean()):.6f}",
                flush=True,
            )


def _print_body_pos_failure_diagnostics(env, topk, step, print_all, detail_names):
    names = getattr(env, "ref_body_pos_names", [])
    errors = getattr(env, "ref_body_pos_world_error", None)
    if errors is None:
        errors = getattr(env, "ref_body_pos_error", None)
    if errors is None or errors.numel() == 0 or not names:
        print(f"body_pos_fail_diag_step: {step}", flush=True)
        print(
            "body_pos_fail_diag_unavailable: motion_body_pos=false matched_bodies=0",
            flush=True,
        )
        return

    failed_mask = env.reset_buf.bool()
    failed_count = int(failed_mask.sum().item())
    print(f"body_pos_fail_diag_step: {step}", flush=True)
    if failed_count == 0:
        print("body_pos_fail_diag: failed_env_count=0", flush=True)
        return

    with torch.no_grad():
        failed_errors = errors[failed_mask]
        failed_env_ids = torch.nonzero(failed_mask, as_tuple=False).flatten()
        first_failed_env = int(failed_env_ids[0])
        first_failed_err = failed_errors[0]
        mean_err = failed_errors.mean(dim=0)
        max_err = failed_errors.max(dim=0).values
        top_count = min(topk, len(names))
        _, top_indices = torch.topk(max_err, k=top_count)

        print(
            "body_pos_fail_diag_columns:"
            " idx name group fail_mean_world_pos_err_m fail_max_world_pos_err_m first_failed_env_world_pos_err_m",
            flush=True,
        )
        print(
            f"body_pos_fail_diag_summary: failed_env_count={failed_count}"
            f" first_failed_env={first_failed_env}",
            flush=True,
        )
        indices = range(len(names)) if print_all else [int(idx) for idx in top_indices]
        for idx in indices:
            name = names[idx]
            print(
                "body_pos_fail_diag:"
                f" {idx} {name} {_joint_group(name)}"
                f" {float(mean_err[idx]):.6f}"
                f" {float(max_err[idx]):.6f}"
                f" {float(first_failed_err[idx]):.6f}",
                flush=True,
            )

        groups = {}
        for idx, name in enumerate(names):
            groups.setdefault(_joint_group(name), []).append(idx)
        for group, indices in sorted(groups.items()):
            index_tensor = torch.tensor(indices, device=env.device)
            print(
                "body_pos_fail_diag_group:"
                f" {group}"
                f" {float(mean_err[index_tensor].mean()):.6f}"
                f" {float(max_err[index_tensor].max()):.6f}"
                f" {float(first_failed_err[index_tensor].mean()):.6f}",
                flush=True,
            )

        if not detail_names:
            return

        detail_indices = _resolve_body_pos_detail_indices(names, detail_names)
        if not detail_indices:
            print(
                "body_pos_fail_detail_unavailable:"
                f" requested={','.join(detail_names)}",
                flush=True,
            )
            return

        body_local = getattr(env, "body_pos_local", None)
        ref_local = getattr(env, "ref_body_pos_local", None)
        local_error_xyz = getattr(env, "ref_body_pos_local_error_xyz", None)
        local_errors = getattr(env, "ref_body_pos_local_error", None)
        if local_error_xyz is None:
            local_error_xyz = getattr(env, "ref_body_pos_error_xyz", None)
        if local_errors is None:
            local_errors = getattr(env, "ref_body_pos_error", None)
        body_world = getattr(env, "body_pos_world", None)
        ref_world = getattr(env, "aligned_ref_body_pos_world", None)
        world_error_xyz = getattr(env, "ref_body_pos_world_error_xyz", None)
        world_errors = getattr(env, "ref_body_pos_world_error", None)
        if body_local is None or ref_local is None or local_error_xyz is None or local_errors is None:
            print("body_pos_fail_detail_unavailable: local_tensors=false", flush=True)
            return

        print(
            "body_pos_fail_detail_columns:"
            " idx name group first_failed_env motion_time_s"
            " local_cur_x local_cur_y local_cur_z"
            " local_ref_x local_ref_y local_ref_z"
            " local_err_x local_err_y local_err_z local_err_norm_m"
            " world_cur_x world_cur_y world_cur_z"
            " world_ref_x world_ref_y world_ref_z world_err_norm_m"
            " fail_mean_err_m fail_max_err_m max_err_env",
            flush=True,
        )
        for idx in detail_indices:
            name = names[idx]
            key_errors = errors[failed_mask, idx]
            max_local_idx = int(torch.argmax(key_errors).item())
            max_env = int(failed_env_ids[max_local_idx])
            cur = body_local[first_failed_env, idx]
            ref = ref_local[first_failed_env, idx]
            delta = local_error_xyz[first_failed_env, idx]
            local_err = local_errors[first_failed_env, idx]
            world_cur = None
            world_ref = None
            world_err = float("nan")
            if body_world is not None and ref_world is not None and body_world.numel() > 0 and ref_world.numel() > 0:
                world_cur = body_world[first_failed_env, idx]
                world_ref = ref_world[first_failed_env, idx]
                if world_errors is not None and world_errors.numel() > 0:
                    world_err = float(world_errors[first_failed_env, idx].item())
                elif world_error_xyz is not None and world_error_xyz.numel() > 0:
                    world_err = float(torch.norm(world_error_xyz[first_failed_env, idx]).item())
                else:
                    world_err = float(torch.norm(world_cur - world_ref).item())
            print(
                "body_pos_fail_detail:"
                f" {idx} {name} {_joint_group(name)}"
                f" {first_failed_env}"
                f" {_motion_time(env, first_failed_env):.6f}"
                f" {float(cur[0]):.6f} {float(cur[1]):.6f} {float(cur[2]):.6f}"
                f" {float(ref[0]):.6f} {float(ref[1]):.6f} {float(ref[2]):.6f}"
                f" {float(delta[0]):.6f} {float(delta[1]):.6f} {float(delta[2]):.6f}"
                f" {float(local_err):.6f}"
                f" {float(world_cur[0]) if world_cur is not None else float('nan'):.6f}"
                f" {float(world_cur[1]) if world_cur is not None else float('nan'):.6f}"
                f" {float(world_cur[2]) if world_cur is not None else float('nan'):.6f}"
                f" {float(world_ref[0]) if world_ref is not None else float('nan'):.6f}"
                f" {float(world_ref[1]) if world_ref is not None else float('nan'):.6f}"
                f" {float(world_ref[2]) if world_ref is not None else float('nan'):.6f}"
                f" {world_err:.6f}"
                f" {float(mean_err[idx]):.6f}"
                f" {float(max_err[idx]):.6f}"
                f" {max_env}",
                flush=True,
            )


def _resolve_body_pos_detail_indices(names, requested_names):
    indices = []
    for requested in requested_names:
        if requested in names:
            indices.append(names.index(requested))
            continue
        matches = [idx for idx, name in enumerate(names) if requested in name]
        indices.extend(matches)
    return sorted(set(indices))


def _motion_time(env, env_id):
    phase = float(env.phase_length_buf[env_id].item()) * float(env.dt)
    offsets = getattr(env, "motion_time_offsets", None)
    if offsets is not None and offsets.numel() > env_id:
        phase += float(offsets[env_id].item())
    return phase


def _print_body_pos_detail_diagnostics(env, step, focus_env, detail_names):
    names = getattr(env, "ref_body_pos_names", [])
    errors = getattr(env, "ref_body_pos_world_error", None)
    if errors is None:
        errors = getattr(env, "ref_body_pos_error", None)
    body_local = getattr(env, "body_pos_local", None)
    ref_local = getattr(env, "ref_body_pos_local", None)
    local_error_xyz = getattr(env, "ref_body_pos_local_error_xyz", None)
    local_errors = getattr(env, "ref_body_pos_local_error", None)
    if local_error_xyz is None:
        local_error_xyz = getattr(env, "ref_body_pos_error_xyz", None)
    if local_errors is None:
        local_errors = getattr(env, "ref_body_pos_error", None)
    body_world = getattr(env, "body_pos_world", None)
    ref_world = getattr(env, "aligned_ref_body_pos_world", None)
    world_error_xyz = getattr(env, "ref_body_pos_world_error_xyz", None)
    world_errors = getattr(env, "ref_body_pos_world_error", None)
    if (
        not detail_names
        or not names
        or errors is None
        or errors.numel() == 0
        or body_local is None
        or ref_local is None
        or local_error_xyz is None
        or local_errors is None
    ):
        return

    indices = _resolve_body_pos_detail_indices(names, detail_names)
    if not indices:
        print(
            "body_pos_detail_unavailable:"
            f" requested={','.join(detail_names)}",
            flush=True,
        )
        return

    env_ids = [max(0, min(focus_env, env.num_envs - 1))]
    failed_ids = torch.nonzero(env.reset_buf.bool(), as_tuple=False).flatten()
    if failed_ids.numel() > 0:
        first_failed_env = int(failed_ids[0])
        if first_failed_env not in env_ids:
            env_ids.append(first_failed_env)

    print(f"body_pos_detail_step: {step}", flush=True)
    print(
        "body_pos_detail_columns:"
        " env_id motion_time_s idx name"
        " local_cur_x local_cur_y local_cur_z"
        " local_ref_x local_ref_y local_ref_z"
        " local_err_x local_err_y local_err_z local_err_norm_m"
        " world_cur_x world_cur_y world_cur_z"
        " world_ref_x world_ref_y world_ref_z world_err_norm_m",
        flush=True,
    )
    with torch.no_grad():
        for env_id in env_ids:
            for idx in indices:
                cur = body_local[env_id, idx]
                ref = ref_local[env_id, idx]
                delta = local_error_xyz[env_id, idx]
                local_err = local_errors[env_id, idx]
                world_cur = None
                world_ref = None
                world_err = float("nan")
                if body_world is not None and ref_world is not None and body_world.numel() > 0 and ref_world.numel() > 0:
                    world_cur = body_world[env_id, idx]
                    world_ref = ref_world[env_id, idx]
                    if world_errors is not None and world_errors.numel() > 0:
                        world_err = float(world_errors[env_id, idx].item())
                    elif world_error_xyz is not None and world_error_xyz.numel() > 0:
                        world_err = float(torch.norm(world_error_xyz[env_id, idx]).item())
                    else:
                        world_err = float(torch.norm(world_cur - world_ref).item())
                print(
                    "body_pos_detail:"
                    f" {env_id}"
                    f" {_motion_time(env, env_id):.6f}"
                    f" {idx} {names[idx]}"
                    f" {float(cur[0]):.6f} {float(cur[1]):.6f} {float(cur[2]):.6f}"
                    f" {float(ref[0]):.6f} {float(ref[1]):.6f} {float(ref[2]):.6f}"
                    f" {float(delta[0]):.6f} {float(delta[1]):.6f} {float(delta[2]):.6f}"
                    f" {float(local_err):.6f}",
                    f" {float(world_cur[0]) if world_cur is not None else float('nan'):.6f}"
                    f" {float(world_cur[1]) if world_cur is not None else float('nan'):.6f}"
                    f" {float(world_cur[2]) if world_cur is not None else float('nan'):.6f}"
                    f" {float(world_ref[0]) if world_ref is not None else float('nan'):.6f}"
                    f" {float(world_ref[1]) if world_ref is not None else float('nan'):.6f}"
                    f" {float(world_ref[2]) if world_ref is not None else float('nan'):.6f}"
                    f" {world_err:.6f}",
                    flush=True,
                )


def _install_ref_keypoint_markers(env):
    if env.headless or env.viewer is None:
        return

    marker_names = _parse_name_list("REF_MARKER_NAMES")
    if not marker_names:
        return

    marker_env = int(os.environ.get("REF_MARKER_ENV", os.environ.get("VIEWER_FOCUS_ENV", "0")))
    if marker_env < 0 or marker_env >= env.num_envs:
        raise ValueError(f"REF_MARKER_ENV={marker_env} is outside num_envs={env.num_envs}")

    radius = float(os.environ.get("REF_MARKER_RADIUS", "0.035"))
    color = _parse_vec("REF_MARKER_COLOR", "1,0,0")
    current_color = _parse_vec("CURRENT_MARKER_COLOR", "0,1,0")
    ref_sphere_geom = gymutil.WireframeSphereGeometry(
        radius,
        8,
        8,
        None,
        color=tuple(color),
    )
    current_sphere_geom = gymutil.WireframeSphereGeometry(
        radius,
        8,
        8,
        None,
        color=tuple(current_color),
    )
    original_render = env.render
    last_unavailable = {"step": -1}

    print(
        "ref_marker.enabled:"
        f" env={marker_env}"
        f" radius={radius}"
        f" ref_color={','.join(str(v) for v in color)}"
        f" current_color={','.join(str(v) for v in current_color)}"
        f" names={','.join(marker_names)}",
        flush=True,
    )

    def render_with_ref_markers(sync_frame_time=True):
        names = getattr(env, "ref_body_pos_names", [])
        ref_body_pos = getattr(env, "aligned_ref_body_pos_world", None)
        body_pos = getattr(env, "body_pos_world", None)
        if (
            names
            and ref_body_pos is not None
            and body_pos is not None
            and ref_body_pos.numel() > 0
            and body_pos.numel() > 0
        ):
            indices = _resolve_body_pos_detail_indices(names, marker_names)
            env.gym.clear_lines(env.viewer)
            with torch.no_grad():
                for idx in indices:
                    ref_pos = ref_body_pos[marker_env, idx]
                    current_pos = body_pos[marker_env, idx]
                    ref_sphere_pose = gymapi.Transform(
                        gymapi.Vec3(float(ref_pos[0]), float(ref_pos[1]), float(ref_pos[2])),
                        r=None,
                    )
                    current_sphere_pose = gymapi.Transform(
                        gymapi.Vec3(
                            float(current_pos[0]),
                            float(current_pos[1]),
                            float(current_pos[2]),
                        ),
                        r=None,
                    )
                    gymutil.draw_lines(
                        ref_sphere_geom,
                        env.gym,
                        env.viewer,
                        env.envs[marker_env],
                        ref_sphere_pose,
                    )
                    gymutil.draw_lines(
                        current_sphere_geom,
                        env.gym,
                        env.viewer,
                        env.envs[marker_env],
                        current_sphere_pose,
                    )
        else:
            step = int(getattr(env, "common_step_counter", 0))
            if step != last_unavailable["step"]:
                print(
                    "ref_marker_unavailable:"
                    " motion_body_pos=false_or_not_initialized",
                    flush=True,
                )
                last_unavailable["step"] = step
        return original_render(sync_frame_time=sync_frame_time)

    env.render = render_with_ref_markers


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


def _install_body_pos_diagnostics(env):
    interval = int(os.environ.get("BODY_POS_DIAG_INTERVAL", "0"))
    if interval <= 0:
        return

    topk = int(os.environ.get("BODY_POS_DIAG_TOPK", "12"))
    fail_interval = int(os.environ.get("BODY_POS_FAIL_DIAG_INTERVAL", str(interval)))
    fail_topk = int(os.environ.get("BODY_POS_FAIL_DIAG_TOPK", str(topk)))
    focus_env = int(os.environ.get("VIEWER_FOCUS_ENV", "0"))
    print_all = _parse_bool("BODY_POS_DIAG_PRINT_ALL")
    print_all = bool(print_all) if print_all is not None else False
    fail_print_all = _parse_bool("BODY_POS_FAIL_DIAG_PRINT_ALL")
    fail_print_all = bool(fail_print_all) if fail_print_all is not None else False
    detail_names = _parse_name_list("BODY_POS_DETAIL_NAMES")
    fail_detail_names = _parse_name_list("BODY_POS_FAIL_DETAIL_NAMES")
    last_printed = {"step": -1}
    last_fail_printed = {"step": -1}
    original_check_termination = env.check_termination

    def check_termination_with_body_pos_diag():
        original_check_termination()
        step = int(getattr(env, "common_step_counter", 0))
        if step > 0 and step % interval == 0 and step != last_printed["step"]:
            _print_body_pos_error_diagnostics(
                env,
                topk=topk,
                step=step,
                focus_env=focus_env,
                print_all=print_all,
            )
            _print_body_pos_detail_diagnostics(
                env,
                step=step,
                focus_env=focus_env,
                detail_names=detail_names,
            )
            last_printed["step"] = step
        if (
            fail_interval > 0
            and step > 0
            and step % fail_interval == 0
            and step != last_fail_printed["step"]
        ):
            _print_body_pos_failure_diagnostics(
                env,
                topk=fail_topk,
                step=step,
                print_all=fail_print_all,
                detail_names=fail_detail_names,
            )
            last_fail_printed["step"] = step

    env.check_termination = check_termination_with_body_pos_diag
    print(
        f"body_pos_diag.enabled: interval={interval} topk={topk} print_all={print_all}",
        flush=True,
    )
    print(
        "body_pos_fail_diag.enabled:"
        f" interval={fail_interval}"
        f" topk={fail_topk}"
        f" print_all={fail_print_all}",
        flush=True,
    )
    if detail_names:
        print(
            "body_pos_detail.enabled:"
            f" names={','.join(detail_names)}",
            flush=True,
        )
    if fail_detail_names:
        print(
            "body_pos_fail_detail.enabled:"
            f" names={','.join(fail_detail_names)}",
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
            world_key_min, world_key_mean, world_key_max = _stats_attr("world_keypoint_termination_error_max")
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
                f" world_keypoint={_sum_bool_attr('termination_world_keypoint_buf')}"
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
                f" world_keypoint_err_min={world_key_min:.6f}"
                f" world_keypoint_err_mean={world_key_mean:.6f}"
                f" world_keypoint_err_max={world_key_max:.6f}"
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
    motion_reference_file = os.environ.get("MOTION_REFERENCE_FILE")
    if motion_cfg is not None and motion_reference_file:
        motion_cfg.file = motion_reference_file
    ref_keypoint_pos_scale = os.environ.get("REF_KEYPOINT_POS_SCALE")
    if ref_keypoint_pos_scale is not None:
        env_cfg.rewards.scales.ref_keypoint_pos = float(ref_keypoint_pos_scale)
    motion_keypoint_pos_sigma = os.environ.get("MOTION_KEYPOINT_POS_SIGMA")
    if motion_keypoint_pos_sigma is not None:
        env_cfg.rewards.motion_keypoint_pos_sigma = float(motion_keypoint_pos_sigma)
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
    if termination_max_ref_joint_pos_error is not None:
        env_cfg.rewards.termination_max_ref_joint_pos_error = _parse_optional_float(
            termination_max_ref_joint_pos_error
        )
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
    _install_ref_keypoint_markers(env)
    _install_joint_diagnostics(env)
    _install_body_pos_diagnostics(env)
    _install_termination_diagnostics(env)
    _install_initial_settle_diagnostics(env)

    ppo_runner, train_cfg, _ = task_registry.make_alg_runner(env=env, name=args.task, args=args, train_cfg=train_cfg)
    ppo_runner.learn(num_learning_iterations=train_cfg.runner.max_iterations, init_at_random_ep_len=False)


if __name__ == "__main__":
    train(get_args())
