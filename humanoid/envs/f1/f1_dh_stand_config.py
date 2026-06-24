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
        file = '{LEGGED_GYM_ROOT_DIR}/resources/robots/f1_v1.5/urdf/F1_29DOF_perfect_mirrored.urdf'
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
        start_time_offset = 0.0

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
        motion_keypoint_pos_sigma = 20.0
        motion_keypoint_pos_tokens = (
            "hip",
            "knee",
            "ankle",
            "toe",
            "lumbar",
            "shoulder",
            "elbow",
            "wrist",
            "neck",
            "head",
        )
        termination_min_base_height = None
        termination_world_keypoint_thresholds = ()
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
        termination_world_keypoint_thresholds = (
            ("ankle", ("ankle",), 0.10),
            ("head_neck", ("head", "neck"), 0.15),
        )

        class scales(F1DHStandCfg.rewards.scales):
            # Motion imitation objectives.
            # Keep joint-angle terms as weak auxiliary priors; prefer spatial imitation rewards.
            ref_joint_pos = 0.1
            ref_lower_body_pos = 1.0
            ref_lumbar_pos = 0.25
            ref_upper_body_pos = 0.1
            ref_keypoint_pos = 10.0
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




class F1RunCfg(F1DHMotionImitationCfg):
    """F1 reference-motion running profile with residual PD imitation."""

    class env(F1DHMotionImitationCfg.env):
        frame_stack = 15
        short_frame_stack = 5
        c_frame_stack = 3
        num_actions = 29
        num_single_obs = 5 + 3 * num_actions + 6
        num_observations = frame_stack * num_single_obs
        single_num_privileged_obs = 21 + 4 * num_actions
        single_linvel_index = 5 + 4 * num_actions
        num_privileged_obs = c_frame_stack * single_num_privileged_obs
        use_ref_actions = True
        use_ref_dof_pos_observation = True
        include_privileged_gait_contact = False

    class control(F1DHMotionImitationCfg.control):
        action_scale = 0.2

    class motion_reference(F1DHMotionImitationCfg.motion_reference):
        # Replace with motion_run_2_1ms_v1_3cycle.npz when that running reference is available.
        stand_uses_default_pose = False
        reset_root_orientation = True
        reset_root_velocity = True
        reset_root_height_offset = 0.0

    class rewards(F1DHMotionImitationCfg.rewards):
        tracking_motion_dof_sigma = 2.0
        tracking_motion_vel_sigma = 1.5
        motion_root_height_sigma = 20.0
        motion_root_orientation_sigma = 4.0
        termination_min_base_height = 0.50
        termination_max_ref_root_xy_distance = None
        termination_max_ref_root_xyz_distance = None
        termination_max_ref_joint_pos_error = None
        termination_ref_joint_grace_steps = 0
        termination_support_rect_margin = None
        termination_world_keypoint_thresholds = ()

        class scales(F1DHMotionImitationCfg.rewards.scales):
            # Core reference-motion imitation objectives.
            tracking_motion_dof = 8.0
            tracking_motion_vel = 7.0

            # Disable the older command/keypoint imitation objectives for this profile.
            ref_joint_pos = 0.0
            ref_lower_body_pos = 0.0
            ref_lumbar_pos = 0.0
            ref_upper_body_pos = 0.0
            ref_keypoint_pos = 0.0
            motion_dof_vel = 0.0
            motion_lower_body_vel = 0.0
            motion_root_height = 3.0
            motion_root_orientation = 2.0
            motion_root_lin_vel = 0.0
            motion_root_ang_vel = 0.0
            motion_contact_schedule = 0.0
            feet_clearance = 0.0
            feet_contact_number = 0.0
            feet_air_time = 0.0
            tracking_lin_vel = 0.0
            tracking_ang_vel = 0.0
            low_speed = 0.0
            track_vel_hard = 0.0
            stand_still = 0.0
            default_joint_pos = 0.0

            # Stability and regularization terms.
            alive = 0.1
            orientation = 0.3
            collision = -2.0
            action_smoothness = -0.002
            action_regularization = -0.02
            torques = -5e-5
            dof_vel = -2e-4
            lin_vel_z = -1.0
            yaw_penalty = -2.0
            dof_pos_limits = -10.0
            feet_rotation = 0.0
            base_height = 0.0
            base_acc = 0.0
            foot_slip = 0.0
            feet_distance = 0.0
            knee_distance = 0.0
            feet_contact_forces = 0.0
            dof_vel_limits = 0.0
            dof_torque_limits = 0.0


class F1RunCfgPPO(F1DHStandCfgPPO):
    class policy(F1DHStandCfgPPO.policy):
        in_channels = F1RunCfg.env.frame_stack
        init_noise_std = 0.25

    class algorithm(F1DHStandCfgPPO.algorithm):
        entropy_coef = 0.0
        learning_rate = 3e-5
        num_learning_epochs = 3
        num_mini_batches = 4
        if F1RunCfg.terrain.measure_heights:
            lin_vel_idx = (
                (F1RunCfg.env.single_num_privileged_obs + F1RunCfg.terrain.num_height)
                * (F1RunCfg.env.c_frame_stack - 1)
                + F1RunCfg.env.single_linvel_index
            )
        else:
            lin_vel_idx = (
                F1RunCfg.env.single_num_privileged_obs
                * (F1RunCfg.env.c_frame_stack - 1)
                + F1RunCfg.env.single_linvel_index
            )

    class runner(F1DHStandCfgPPO.runner):
        num_steps_per_env = 24
        experiment_name = "f1_run"

class F1RunPhase0Cfg(F1RunCfg):
    """Early curriculum for residual imitation from a fixed reference phase."""

    class motion_reference(F1RunCfg.motion_reference):
        randomize_start_phase = False
        start_time_offset = 0.0


class F1RunPhase0CfgPPO(F1RunCfgPPO):
    class runner(F1RunCfgPPO.runner):
        experiment_name = "f1_run_phase0"


class F1RunRephaseCfg(F1RunCfg):
    """Early curriculum using a rephased walking reference with a stable first frame."""

    class rewards(F1RunCfg.rewards):
        motion_root_height_sigma = 8.0
        motion_root_orientation_sigma = 3.0
        motion_root_height_error_tolerance = 0.02
        base_height_floor = 0.58
        termination_min_base_height = 0.34

        class scales(F1RunCfg.rewards.scales):
            motion_root_height = 20.0
            motion_root_height_error = -48.0
            base_height_floor_error = -240.0
            motion_root_orientation = 4.0
            motion_contact_schedule = 4.0

    class motion_reference(F1RunCfg.motion_reference):
        file = (
            '{LEGGED_GYM_ROOT_DIR}/resources/motions/f1/v1.5/processed/'
            '07_03_walk_yup_recwalk_base_lowerbody_smooth_p8_120_180_groundfit_minima_safe_rephase_stable_bodypos.npz'
        )
        randomize_start_phase = False
        start_time_offset = 0.0


class F1RunRephaseCfgPPO(F1RunCfgPPO):
    class policy(F1RunCfgPPO.policy):
        init_noise_std = 0.4

    class runner(F1RunCfgPPO.runner):
        experiment_name = "f1_run_rephase"


class F1RunStaticStandCfg(F1RunCfg):
    """Run-policy-compatible standing warm-up before dynamic reference imitation."""

    class asset(F1RunCfg.asset):
        terminate_after_contacts_on = []

    class terrain(F1RunCfg.terrain):
        mesh_type = 'plane'
        measure_heights = False
        curriculum = False
        max_init_terrain_level = 0
        num_rows = 1
        num_cols = 1

    class noise(F1RunCfg.noise):
        add_noise = False

    class domain_rand(F1RunCfg.domain_rand):
        randomize_friction = False
        push_robots = False
        add_ext_force = False
        randomize_base_mass = False
        randomize_com = False
        randomize_link_com = False
        randomize_base_inertia = False
        randomize_link_inertia = False
        randomize_gains = False
        randomize_torque = False
        randomize_link_mass = False
        randomize_motor_offset = False
        randomize_joint_friction = False
        randomize_joint_damping = False
        randomize_joint_armature = False
        add_lag = False
        add_dof_lag = False
        add_dof_pos_vel_lag = False
        add_imu_lag = False
        randomize_coulomb_friction = False

    class control(F1RunCfg.control):
        action_scale = 0.02

    class init_state(F1RunCfg.init_state):
        # MJCF home_default all-zero pose, frozen as a static reference.
        default_joint_angles = {
            'left_hip_pitch_joint': 0.000000000,
            'left_hip_roll_joint': 0.000000000,
            'left_hip_yaw_joint': 0.000000000,
            'left_knee_pitch_joint': 0.000000000,
            'left_ankle_pitch_joint': 0.000000000,
            'left_ankle_roll_joint': 0.000000000,
            'lumbar_yaw_joint': 0.000000000,
            'lumbar_roll_joint': 0.000000000,
            'lumbar_pitch_joint': 0.000000000,
            'left_shoulder_pitch_joint': 0.000000000,
            'left_shoulder_roll_joint': 0.000000000,
            'left_shoulder_yaw_joint': 0.000000000,
            'left_elbow_pitch_joint': 0.000000000,
            'left_elbow_yaw_joint': 0.000000000,
            'left_wrist_pitch_joint': 0.000000000,
            'left_wrist_roll_joint': 0.000000000,
            'right_shoulder_pitch_joint': 0.000000000,
            'right_shoulder_roll_joint': 0.000000000,
            'right_shoulder_yaw_joint': 0.000000000,
            'right_elbow_pitch_joint': 0.000000000,
            'right_elbow_yaw_joint': 0.000000000,
            'right_wrist_pitch_joint': 0.000000000,
            'right_wrist_roll_joint': 0.000000000,
            'right_hip_pitch_joint': 0.000000000,
            'right_hip_roll_joint': 0.000000000,
            'right_hip_yaw_joint': 0.000000000,
            'right_knee_pitch_joint': 0.000000000,
            'right_ankle_pitch_joint': 0.000000000,
            'right_ankle_roll_joint': 0.000000000,
        }
    class motion_reference(F1RunCfg.motion_reference):
        file = (
            '{LEGGED_GYM_ROOT_DIR}/resources/motions/f1/v1.5/processed/'
            'f1_zero_static_stand_bodypos.npz'
        )
        randomize_start_phase = False
        playback_speed = 0.0
        stand_uses_default_pose = False
        reset_root_height_offset = 0.0
        align_ref_root_height_on_reset = False
        reset_root_orientation = True
        reset_root_velocity = True

    class rewards(F1RunCfg.rewards):
        motion_root_height_sigma = 8.0
        motion_root_orientation_sigma = 3.0
        motion_root_height_error_tolerance = 0.02
        motion_keypoint_pos_sigma = 35.0
        motion_keypoint_max_pos_sigma = 45.0
        motion_keypoint_ankle_sigma = 60.0
        motion_keypoint_knee_sigma = 45.0
        motion_keypoint_hip_lumbar_sigma = 40.0
        motion_keypoint_base_head_sigma = 35.0
        motion_keypoint_upper_body_sigma = 25.0
        motion_keypoint_pos_tokens = (
            "ankle", "knee", "hip", "lumbar",
            "base", "neck", "head", "shoulder", "elbow",
        )
        base_height_floor = 0.58
        termination_min_base_height = 0.50
        termination_max_ref_root_xy_distance = None
        termination_max_ref_root_xyz_distance = None
        termination_max_ref_joint_pos_error = None
        termination_ref_joint_grace_steps = 0
        termination_support_rect_margin = None
        termination_world_keypoint_thresholds = (
            ("ankle", ("ankle",), 0.05),
            ("knee", ("knee",), 0.10),
            ("hip_lumbar", ("hip", "lumbar"), 0.10),
            ("base_head", ("base", "head", "neck"), 0.15),
            ("upper_body", ("shoulder", "elbow"), 0.15),
        )

        class scales(F1RunCfg.rewards.scales):
            tracking_motion_dof = 10.0
            tracking_motion_vel = 4.0
            motion_root_height = 30.0
            motion_root_height_error = -64.0
            base_height_floor_error = -260.0
            motion_root_orientation = 18.0
            ref_keypoint_pos = 25.0
            ref_keypoint_ankle_pos = 35.0
            ref_keypoint_knee_pos = 25.0
            ref_keypoint_hip_lumbar_pos = 25.0
            ref_keypoint_base_head_pos = 20.0
            ref_keypoint_upper_body_pos = 10.0
            motion_contact_schedule = 0.0
            orientation = 4.0
            action_regularization = -0.20
            action_smoothness = -0.02
            torques = -1e-4
            dof_vel = -5e-4
            yaw_penalty = -0.5


class F1RunStaticStandCfgPPO(F1RunCfgPPO):
    class policy(F1RunCfgPPO.policy):
        init_noise_std = 0.01

    class algorithm(F1RunCfgPPO.algorithm):
        learning_rate = 3e-5
        entropy_coef = 0.0
        num_learning_epochs = 3

    class runner(F1RunCfgPPO.runner):
        experiment_name = "f1_run_static_stand"

class F1DHStaticStandCfg(F1DHMotionImitationCfg):
    """F1 standing profile using one stable retargeted CSV frame as reference."""

    class init_state(F1DHMotionImitationCfg.init_state):
        # Frame 0 of motion_walk_0.6ms.csv. The CSV joint columns are radians.
        default_joint_angles = {
            'lumbar_yaw_joint': 0.704135000,
            'lumbar_roll_joint': 0.016613000,
            'lumbar_pitch_joint': -0.110219000,
            'left_shoulder_pitch_joint': 0.154395000,
            'left_shoulder_roll_joint': -0.072362000,
            'left_shoulder_yaw_joint': 0.470767000,
            'left_elbow_pitch_joint': 0.198862000,
            'left_elbow_yaw_joint': 0.007941000,
            'left_wrist_pitch_joint': 0.000000000,
            'left_wrist_roll_joint': 0.000000000,
            'right_shoulder_pitch_joint': -0.156507000,
            'right_shoulder_roll_joint': -0.080209000,
            'right_shoulder_yaw_joint': 0.654353000,
            'right_elbow_pitch_joint': 0.177029000,
            'right_elbow_yaw_joint': 0.004934000,
            'right_wrist_pitch_joint': 0.000000000,
            'right_wrist_roll_joint': 0.000000000,
            'left_hip_pitch_joint': 0.370413000,
            'left_hip_roll_joint': -0.137790000,
            'left_hip_yaw_joint': 0.709049000,
            'left_knee_pitch_joint': 0.126784000,
            'left_ankle_pitch_joint': -0.008630000,
            'left_ankle_roll_joint': -0.241372667,
            'right_hip_pitch_joint': 0.560208000,
            'right_hip_roll_joint': 0.096614000,
            'right_hip_yaw_joint': -0.190644000,
            'right_knee_pitch_joint': 0.050529000,
            'right_ankle_pitch_joint': 0.160375765,
            'right_ankle_roll_joint': -0.146468667,
        }

    class motion_reference(F1DHMotionImitationCfg.motion_reference):
        file = (
            '{LEGGED_GYM_ROOT_DIR}/resources/motions/f1/v1.5/processed/'
            'motion_walk_0.6ms_static_stand_frame0_bodypos.npz'
        )
        randomize_start_phase = False
        playback_speed = 0.0
        stand_uses_default_pose = False
        reset_root_height_offset = 0.0
        reset_root_orientation = True
        reset_root_velocity = True

    class rewards(F1DHMotionImitationCfg.rewards):
        termination_min_base_height = 0.52
        termination_max_ref_root_xy_distance = 0.30
        termination_max_ref_root_xyz_distance = None
        termination_max_ref_joint_pos_error = None
        termination_ref_joint_grace_steps = 0
        termination_support_rect_margin = 0.05
        termination_world_keypoint_thresholds = (
            ("ankle", ("ankle",), 0.15),
            ("head_neck", ("head", "neck"), 0.20),
        )

        class scales(F1DHMotionImitationCfg.rewards.scales):
            ref_joint_pos = 1.0
            ref_lower_body_pos = 2.0
            ref_lumbar_pos = 0.5
            ref_upper_body_pos = 0.2
            ref_keypoint_pos = 10.0
            motion_dof_vel = 2.0
            motion_lower_body_vel = 2.0
            motion_root_height = 3.0
            motion_root_orientation = 3.0
            motion_root_lin_vel = 2.0
            motion_root_ang_vel = 1.0
            tracking_lin_vel = 0.0
            tracking_ang_vel = 0.0
            feet_clearance = 0.0
            feet_distance = 0.1
            knee_distance = 0.1
            foot_slip = -0.10
            default_joint_pos = 0.0


class F1DHStaticStandCfgPPO(F1DHMotionImitationCfgPPO):
    class policy(F1DHMotionImitationCfgPPO.policy):
        init_noise_std = 0.08

    class algorithm(F1DHMotionImitationCfgPPO.algorithm):
        learning_rate = 5e-6
        entropy_coef = 0.0
        num_learning_epochs = 1
        num_mini_batches = 2

    class runner(F1DHMotionImitationCfgPPO.runner):
        num_steps_per_env = 48
        experiment_name = 'f1_dh_static_stand'

