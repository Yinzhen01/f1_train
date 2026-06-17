# Copyright (c) 2024, AgiBot Inc. All rights reserved.

from humanoid.envs.x1.x1_dh_stand_config import X1DHStandCfg, X1DHStandCfgPPO


class F1DHStandCfg(X1DHStandCfg):
    """Configuration for F1 29-DOF training."""

    class env(X1DHStandCfg.env):
        num_actions = 29
        num_single_obs = 5 + 3 * num_actions + 6
        num_observations = int(X1DHStandCfg.env.frame_stack * num_single_obs)
        single_num_privileged_obs = 25 + 4 * num_actions
        single_linvel_index = 5 + 4 * num_actions
        num_privileged_obs = int(X1DHStandCfg.env.c_frame_stack * single_num_privileged_obs)

    class asset(X1DHStandCfg.asset):
        file = '{LEGGED_GYM_ROOT_DIR}/resources/robots/f1_v1.5/urdf/F1_29DOF_physically_mirrored.urdf'
        xml_file = ''
        name = "f1"

    class motion_reference:
        enabled = True
        file = (
            '{LEGGED_GYM_ROOT_DIR}/resources/motions/f1/v1.5/processed/'
            '07_03_walk_yup_recwalk_base_lowerbody_smooth_p8_120_180_groundfit_minima_safe.npz'
        )
        randomize_start_phase = True
        playback_speed = 1.0
        stand_uses_default_pose = True
        reset_dofs_to_motion = True
        reset_root_height = True
        reset_root_orientation = False
        reset_root_velocity = False
        reset_root_height_offset = 0.0

    class init_state(X1DHStandCfg.init_state):
        # Retargeted first frame from:
        # /home/yinzhen/f1_sim/07_PHUMA/data/humanoid_pose/f1/v1.4/custom_walk/07_03_walk_yup_stitched.csv
        pos = [0.0, 0.0, 0.7]
        default_joint_angles = {
            'lumbar_yaw_joint': -0.291405,
            'lumbar_roll_joint': 0.056444,
            'lumbar_pitch_joint': 0.029333,
            'left_shoulder_pitch_joint': 0.070985,
            'left_shoulder_roll_joint': -0.060964,
            'left_shoulder_yaw_joint': 0.395337,
            'left_elbow_pitch_joint': 0.731528,
            'left_elbow_yaw_joint': 0.019666,
            'left_wrist_pitch_joint': 0.0,
            'left_wrist_roll_joint': 0.0,
            'right_shoulder_pitch_joint': 0.125797,
            'right_shoulder_roll_joint': -0.000969,
            'right_shoulder_yaw_joint': 0.908459,
            'right_elbow_pitch_joint': 0.244263,
            'right_elbow_yaw_joint': 0.004876,
            'right_wrist_pitch_joint': 0.0,
            'right_wrist_roll_joint': 0.0,
            'left_hip_pitch_joint': -0.521958,
            'left_hip_roll_joint': 0.143144,
            'left_hip_yaw_joint': 0.437506,
            'left_knee_pitch_joint': 0.555748,
            'left_ankle_pitch_joint': -0.215109,
            'left_ankle_roll_joint': 0.386691,
            'right_hip_pitch_joint': -0.434993,
            'right_hip_roll_joint': -0.081053,
            'right_hip_yaw_joint': 0.152487,
            'right_knee_pitch_joint': 0.472142,
            'right_ankle_pitch_joint': -0.039060,
            'right_ankle_roll_joint': 0.080306,
        }

    class control(X1DHStandCfg.control):
        stiffness = {
            'lumbar_yaw_joint': 80, 'lumbar_roll_joint': 80, 'lumbar_pitch_joint': 100,
            'shoulder_pitch_joint': 20, 'shoulder_roll_joint': 20, 'shoulder_yaw_joint': 20,
            'elbow_pitch_joint': 20, 'elbow_yaw_joint': 15,
            'wrist_pitch_joint': 8, 'wrist_roll_joint': 8,
            'hip_pitch_joint': 30, 'hip_roll_joint': 40, 'hip_yaw_joint': 35,
            'knee_pitch_joint': 100, 'ankle_pitch_joint': 35, 'ankle_roll_joint': 35,
        }
        damping = {
            'lumbar_yaw_joint': 5, 'lumbar_roll_joint': 5, 'lumbar_pitch_joint': 6,
            'shoulder_pitch_joint': 1.5, 'shoulder_roll_joint': 1.5, 'shoulder_yaw_joint': 1.5,
            'elbow_pitch_joint': 1.2, 'elbow_yaw_joint': 1.0,
            'wrist_pitch_joint': 0.5, 'wrist_roll_joint': 0.5,
            'hip_pitch_joint': 3, 'hip_roll_joint': 3.0, 'hip_yaw_joint': 4,
            'knee_pitch_joint': 10, 'ankle_pitch_joint': 0.5, 'ankle_roll_joint': 0.5,
        }
        # Per-DOF scale in Isaac Gym F1 asset order. Values are based on the retargeted
        # motion range around the first frame, with small scales for missing wrists.
        action_scale = [
            1.10, 0.40, 0.85, 0.80, 0.45, 0.45,
            0.70, 0.10, 0.10,
            0.35, 0.06, 0.45, 0.20, 0.03, 0.05, 0.05,
            0.40, 0.06, 0.45, 0.28, 0.03, 0.05, 0.05,
            1.00, 0.45, 0.60, 0.80, 0.20, 0.35,
        ]

    class rewards(X1DHStandCfg.rewards):
        motion_dof_vel_sigma = 0.15
        motion_root_height_sigma = 100.0
        motion_root_orientation_sigma = 8.0
        motion_root_lin_vel_sigma = 4.0
        motion_root_ang_vel_sigma = 3.0
        termination_min_base_height = None
        termination_max_ref_root_xy_distance = None
        termination_max_ref_root_xyz_distance = None
        termination_max_ref_joint_pos_error = None
        termination_ref_joint_grace_steps = 0
        termination_support_rect_margin = None


class F1DHStandCfgPPO(X1DHStandCfgPPO):
    class policy(X1DHStandCfgPPO.policy):
        in_channels = F1DHStandCfg.env.frame_stack

    class algorithm(X1DHStandCfgPPO.algorithm):
        if F1DHStandCfg.terrain.measure_heights:
            lin_vel_idx = (
                (F1DHStandCfg.env.single_num_privileged_obs + F1DHStandCfg.terrain.num_height)
                * (F1DHStandCfg.env.c_frame_stack - 1)
                + F1DHStandCfg.env.single_linvel_index
            )
        else:
            lin_vel_idx = (
                F1DHStandCfg.env.single_num_privileged_obs
                * (F1DHStandCfg.env.c_frame_stack - 1)
                + F1DHStandCfg.env.single_linvel_index
            )

    class runner(X1DHStandCfgPPO.runner):
        experiment_name = 'f1_dh_stand'


class F1DHMotionImitationCfg(F1DHStandCfg):
    """F1 training profile that prioritizes retargeted motion imitation."""

    class env(F1DHStandCfg.env):
        use_ref_actions = True

    class motion_reference(F1DHStandCfg.motion_reference):
        stand_uses_default_pose = False
        reset_root_orientation = True
        reset_root_velocity = True
        reset_root_height_offset = -0.012

    class commands(F1DHStandCfg.commands):
        curriculum = False
        gait = ["walk_omnidirectional"]
        sw_switch = False
        stand_com_threshold = -1.0

    class rewards(F1DHStandCfg.rewards):
        termination_min_base_height = 0.50
        termination_max_ref_root_xy_distance = 0.5
        termination_max_ref_root_xyz_distance = None
        termination_max_ref_joint_pos_error = None
        termination_ref_joint_grace_steps = 0
        termination_support_rect_margin = 0.10

        class scales(F1DHStandCfg.rewards.scales):
            # Motion imitation objectives.
            # These compare DOF angles, not Cartesian body/keypoint positions.
            # Keep them as weak auxiliary priors; prefer spatial imitation rewards.
            ref_joint_pos = 0.1
            ref_lower_body_pos = 1.0
            ref_lumbar_pos = 0.25
            ref_upper_body_pos = 0.1
            motion_dof_vel = 1.0
            motion_lower_body_vel = 1.5
            motion_root_height = 2.0
            motion_root_orientation = 1.5
            motion_root_lin_vel = 1.0
            motion_root_ang_vel = 0.5
            # Current NPZ has no foot contact labels yet; enable after adding foot_contacts.
            motion_contact_schedule = 0.0

            # Old gait/command heuristics reduced or disabled.
            feet_clearance = 0.1
            feet_contact_number = 0.0
            feet_air_time = 0.0
            tracking_lin_vel = 0.2
            tracking_ang_vel = 0.1
            low_speed = 0.0
            track_vel_hard = 0.0
            stand_still = 0.0
            default_joint_pos = 0.2

            # Stability and safety guards.
            orientation = 0.3
            feet_rotation = 0.1
            base_height = 0.0
            base_acc = 0.1
            foot_slip = -0.08
            feet_distance = 0.15
            knee_distance = 0.15
            feet_contact_forces = -0.01
            action_smoothness = -0.002
            torques = -8e-9
            dof_vel = -1e-8
            dof_acc = -1e-7
            collision = -1.0
            dof_vel_limits = -1.0
            dof_pos_limits = -10.0
            dof_torque_limits = -0.1


class F1DHMotionImitationCfgPPO(F1DHStandCfgPPO):
    class policy(F1DHStandCfgPPO.policy):
        init_noise_std = 0.12

    class algorithm(F1DHStandCfgPPO.algorithm):
        entropy_coef = 0.0
        learning_rate = 5e-6
        num_learning_epochs = 1
        num_mini_batches = 2

    class runner(F1DHStandCfgPPO.runner):
        num_steps_per_env = 48
        experiment_name = 'f1_dh_motion_imitation'
