# F1 Checkpoint Inference Handoff

本文档用于回答推理端对 F1 29DOF checkpoint 的部署对接问题。

## 1. Checkpoint 与训练代码版本

当前建议讨论的 checkpoint：

```text
TASK_20260611_032/checkpoints/model_5.pt
```

对应任务：

```text
task: f1_dh_motion_imitation
commit: 979ab05a34c621967ab9bfd67dc8abe1960761fa
```

对应训练代码文件：

```text
humanoid/envs/f1/f1_dh_stand_config.py
humanoid/envs/f1/f1_dh_stand_env.py
humanoid/algo/ppo/actor_critic_dh.py
```

当前仓库 HEAD 已到：

```text
a94b2a5949755cbee21886ceb73709dfb6613302
```

但从 `979ab05a34c621967ab9bfd67dc8abe1960761fa` 到当前 HEAD，上述三个训练相关文件没有变化。

已有任务区分：

| Task ID | Task | Commit | 说明 |
|---|---|---|---|
| `TASK_20260611_003` | `f1_dh_stand` | `c8c53fe793646039f4a1d2d27705838842750cf0` | stand 短训，20 iter |
| `TASK_20260611_007` | `f1_dh_stand` | `0f16582068ec5cf3231f4ded5230d18729daac57` | DOF order smoke，5 iter |
| `TASK_20260611_032` | `f1_dh_motion_imitation` | `979ab05a34c621967ab9bfd67dc8abe1960761fa` | motion imitation smoke，5 iter |

## 2. 部署应导出哪个网络

建议导出完整 policy wrapper，不要只导出 bare actor。

完整 wrapper 包括：

```text
long_history CNN
state_estimator
actor MLP
```

运行端输入应为：

```text
[1, 6468] = [1, 66 x 98]
```

也就是 66 帧历史观测，每帧 98 维。

不要直接给 `[1, 557]`，除非推理端自己实现了 history CNN 和 state estimator，并且只想调用 bare actor。

## 3. 557 维 Actor 输入拆分

如果只导出 actor，actor 输入是：

```text
557 = 490 + 3 + 64
```

| 维度 | 含义 |
|---:|---|
| `490` | short history，`5 x 98` |
| `3` | state estimator 输出的 base linear velocity 估计 |
| `64` | long-history CNN 输出 latent |

privileged obs 只用于 critic 训练，不参与部署。

## 4. 运行端真实输入

推荐 C++ 直接喂完整 wrapper：

```text
input shape: [1, 6468]
```

由导出的 JIT/ONNX 内部完成：

```text
66 帧 history -> long_history CNN
最后 5 帧 short history -> state_estimator
拼接 557 维 actor 输入 -> actor 输出 29 维 action
```

不是 `[1, 47 x 66]`。`47` 是旧 X1/12DOF 单帧观测维度；F1 29DOF 单帧是 `98`。

## 5. 98 维基础观测顺序

单帧 obs 维度：

```text
98 = 5 + 29 + 29 + 29 + 3 + 3
```

精确顺序：

| Index | 维度 | 内容 | Scale |
|---:|---:|---|---:|
| `0` | 1 | `sin(phase)` | 1.0 |
| `1` | 1 | `cos(phase)` | 1.0 |
| `2` | 1 | `cmd_vx` | 2.0 |
| `3` | 1 | `cmd_vy` | 2.0 |
| `4` | 1 | `cmd_yaw_rate` | 1.0 |
| `5:34` | 29 | `q - default_q` | 1.0 |
| `34:63` | 29 | `dq` | 0.05 |
| `63:92` | 29 | `previous_action` | 1.0 |
| `92:95` | 3 | base angular velocity | 1.0 |
| `95:98` | 3 | base Euler XYZ | 1.0 |

说明：

```text
使用 Euler XYZ，不是 projected gravity。
cmd_vel 会缩放。
phase 存在。
clip_observations = 100
clip_actions = 100
cycle_time = 0.7s
```

`previous_action` 对 `TASK_20260611_032` 来说，应理解为上一帧实际进入训练环境 step 的 action，也就是包含 `ref_action` 后并 clip 的 action。

## 6. 29 个 Action / Joint 顺序

训练端使用 Isaac Gym / URDF DOF 顺序：

| Index | Joint |
|---:|---|
| 1 | `lumbar_yaw_joint` |
| 2 | `lumbar_roll_joint` |
| 3 | `lumbar_pitch_joint` |
| 4 | `left_shoulder_pitch_joint` |
| 5 | `left_shoulder_roll_joint` |
| 6 | `left_shoulder_yaw_joint` |
| 7 | `left_elbow_pitch_joint` |
| 8 | `left_elbow_yaw_joint` |
| 9 | `left_wrist_pitch_joint` |
| 10 | `left_wrist_roll_joint` |
| 11 | `right_shoulder_pitch_joint` |
| 12 | `right_shoulder_roll_joint` |
| 13 | `right_shoulder_yaw_joint` |
| 14 | `right_elbow_pitch_joint` |
| 15 | `right_elbow_yaw_joint` |
| 16 | `right_wrist_pitch_joint` |
| 17 | `right_wrist_roll_joint` |
| 18 | `left_hip_pitch_joint` |
| 19 | `left_hip_roll_joint` |
| 20 | `left_hip_yaw_joint` |
| 21 | `left_knee_pitch_joint` |
| 22 | `left_ankle_pitch_joint` |
| 23 | `left_ankle_roll_joint` |
| 24 | `right_hip_pitch_joint` |
| 25 | `right_hip_roll_joint` |
| 26 | `right_hip_yaw_joint` |
| 27 | `right_knee_pitch_joint` |
| 28 | `right_ankle_pitch_joint` |
| 29 | `right_ankle_roll_joint` |

注意：仓库里的 F1 MJCF actuator 顺序与训练顺序不一致。推理端如果用 MuJoCo actuator，必须按 joint name 重排，不能直接把 29 维 action 原样塞给 actuator。

仓库中 `resources/robots/f1_v1.5/mjcf/robot/xyber_f1/F1_29DOF.xml` 的 actuator 顺序为：

| MJCF Actuator Index | Joint |
|---:|---|
| 1 | `left_hip_pitch_joint` |
| 2 | `left_hip_roll_joint` |
| 3 | `left_hip_yaw_joint` |
| 4 | `left_knee_pitch_joint` |
| 5 | `left_ankle_pitch_joint` |
| 6 | `left_ankle_roll_joint` |
| 7 | `right_hip_pitch_joint` |
| 8 | `right_hip_roll_joint` |
| 9 | `right_hip_yaw_joint` |
| 10 | `right_knee_pitch_joint` |
| 11 | `right_ankle_pitch_joint` |
| 12 | `right_ankle_roll_joint` |
| 13 | `lumbar_yaw_joint` |
| 14 | `lumbar_roll_joint` |
| 15 | `lumbar_pitch_joint` |
| 16 | `left_shoulder_pitch_joint` |
| 17 | `left_shoulder_roll_joint` |
| 18 | `left_shoulder_yaw_joint` |
| 19 | `left_elbow_pitch_joint` |
| 20 | `left_elbow_yaw_joint` |
| 21 | `left_wrist_pitch_joint` |
| 22 | `right_shoulder_pitch_joint` |
| 23 | `right_shoulder_roll_joint` |
| 24 | `right_shoulder_yaw_joint` |
| 25 | `right_elbow_pitch_joint` |
| 26 | `right_elbow_yaw_joint` |
| 27 | `right_wrist_pitch_joint` |
| 28 | `left_wrist_roll_joint` |
| 29 | `right_wrist_roll_joint` |

## 7. Action 后处理规则

`action_scale` 是 per-joint 数组：

```text
[1.10, 0.40, 0.85, 0.80, 0.45, 0.45,
 0.70, 0.10, 0.10,
 0.35, 0.06, 0.45, 0.20, 0.03, 0.05, 0.05,
 0.40, 0.06, 0.45, 0.28, 0.03, 0.05, 0.05,
 1.00, 0.45, 0.60, 0.80, 0.20, 0.35]
```

普通 stand policy 的位置目标：

```text
target_q = default_q + clip(action, -100, 100) * action_scale
```

但 `TASK_20260611_032` 是 motion imitation，训练时配置：

```text
use_ref_actions = True
```

所以实际规则是：

```text
final_action = clip(network_output + ref_action, -100, 100)
target_q = default_q + final_action * action_scale
```

网络输出不是 torque，而是目标关节位置相对默认姿态的增量。PD 再把位置目标转成 torque。

训练端没有显式 LPF。训练控制参数：

```text
sim.dt = 0.001
decimation = 10
policy rate = 100 Hz
```

## 8. 默认姿态

默认姿态来自 `F1DHStandCfg.init_state.default_joint_angles`，按训练 joint 顺序如下：

| Index | Joint | Default Angle |
|---:|---|---:|
| 1 | `lumbar_yaw_joint` | -0.291405 |
| 2 | `lumbar_roll_joint` | 0.056444 |
| 3 | `lumbar_pitch_joint` | 0.029333 |
| 4 | `left_shoulder_pitch_joint` | 0.070985 |
| 5 | `left_shoulder_roll_joint` | -0.060964 |
| 6 | `left_shoulder_yaw_joint` | 0.395337 |
| 7 | `left_elbow_pitch_joint` | 0.731528 |
| 8 | `left_elbow_yaw_joint` | 0.019666 |
| 9 | `left_wrist_pitch_joint` | 0.0 |
| 10 | `left_wrist_roll_joint` | 0.0 |
| 11 | `right_shoulder_pitch_joint` | 0.125797 |
| 12 | `right_shoulder_roll_joint` | -0.000969 |
| 13 | `right_shoulder_yaw_joint` | 0.908459 |
| 14 | `right_elbow_pitch_joint` | 0.244263 |
| 15 | `right_elbow_yaw_joint` | 0.004876 |
| 16 | `right_wrist_pitch_joint` | 0.0 |
| 17 | `right_wrist_roll_joint` | 0.0 |
| 18 | `left_hip_pitch_joint` | -0.521958 |
| 19 | `left_hip_roll_joint` | 0.143144 |
| 20 | `left_hip_yaw_joint` | 0.437506 |
| 21 | `left_knee_pitch_joint` | 0.555748 |
| 22 | `left_ankle_pitch_joint` | -0.215109 |
| 23 | `left_ankle_roll_joint` | 0.386691 |
| 24 | `right_hip_pitch_joint` | -0.434993 |
| 25 | `right_hip_roll_joint` | -0.081053 |
| 26 | `right_hip_yaw_joint` | 0.152487 |
| 27 | `right_knee_pitch_joint` | 0.472142 |
| 28 | `right_ankle_pitch_joint` | -0.039060 |
| 29 | `right_ankle_roll_joint` | 0.080306 |

## 9. PD 参数

PD 参数按 joint name 匹配：

| Joint Pattern | Stiffness | Damping |
|---|---:|---:|
| `lumbar_yaw_joint` | 80 | 5 |
| `lumbar_roll_joint` | 80 | 5 |
| `lumbar_pitch_joint` | 100 | 6 |
| `shoulder_pitch_joint` | 20 | 1.5 |
| `shoulder_roll_joint` | 20 | 1.5 |
| `shoulder_yaw_joint` | 20 | 1.5 |
| `elbow_pitch_joint` | 20 | 1.2 |
| `elbow_yaw_joint` | 15 | 1.0 |
| `wrist_pitch_joint` | 8 | 0.5 |
| `wrist_roll_joint` | 8 | 0.5 |
| `hip_pitch_joint` | 30 | 3 |
| `hip_roll_joint` | 40 | 3.0 |
| `hip_yaw_joint` | 35 | 4 |
| `knee_pitch_joint` | 100 | 10 |
| `ankle_pitch_joint` | 35 | 0.5 |
| `ankle_roll_joint` | 35 | 0.5 |

训练端没有单独区分串联/并联关节，统一按 29 个 actuated DOF 做 PD。

## 10. History Buffer 初始化和更新

训练端初始化：

```text
66 帧 obs history 全 0
reset 时对应 env 的 history 也清零
```

更新方式：

```text
每个 policy step append 当前 98 维 obs
popleft 最老帧
flatten 成 [66 x 98]
```

不是全填第一帧。

## 11. 部署提醒

`TASK_20260611_032` 是 motion imitation smoke checkpoint，并且依赖 `ref_action`。

如果推理端没有同步实现参考轨迹相位和 `ref_action`，这个 checkpoint 不能当普通 stand/walk policy 直接部署。

当前它更适合验证链路、维度、导出和动作顺序；真正上机建议后续使用明确的长训部署 checkpoint，并确认是否保留 `ref_action` 机制。
