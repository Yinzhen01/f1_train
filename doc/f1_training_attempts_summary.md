# F1 训练尝试与阶段性结论

日期：2026-06-23

本文整理截至目前 F1 29DOF 训练中做过的主要尝试、每次调整背后的思路、实际效果，以及后续建议。重点覆盖 Gradmotion 云端训练、motion imitation 奖励配置、完整 5000 iteration 训练、后续 static stand / rephase / keypoint 路线。

## 总体结论

目前最明确的结论是：

1. 云端训练链路已经打通：GitHub 拉代码、Isaac Gym 启动、F1 29DOF 注册、checkpoint 上传、日志下载和同步到 infer 目录都已验证。
2. `f1_dh_motion_imitation` 的 1024 env / 5000 iteration 正式训练完整跑完，但策略效果不理想：最终 `Mean reward` 接近 0，`Mean episode length` 约 36.78，说明直接做长序列运动模仿还没有得到稳定可用的行走策略。
3. 4096 env 的正式训练没有进入容器执行阶段，失败在平台调度/启动前；1024 env 可以稳定跑完。
4. 后续方向已经从“直接全轨迹模仿”转向“先稳定站立，再短片段/重相位行走模仿，最后扩展到完整行走”。
5. 最新 static stand / run-static warm-up 路线已有本地 rollout 产物，但 `model_3000` 仍未稳定站住：6 秒 rollout 中 root 高度最低到 0.129m，说明还存在明显倒伏/塌落。

## 关键任务时间线

| 阶段 | 任务/配置 | 目的 | 结果 |
| --- | --- | --- | --- |
| 云端基线 | `TASK_20260608_073` / `f1_dh_stand` / 5 iter | 验证 Gradmotion + Isaac Gym + public GitHub 拉取 | Completed，证明基础云端链路可用 |
| F1 ref pose 短训 | `TASK_20260611_003` / `f1_dh_stand` / 64 env / 20 iter | 验证 F1 v1.5 ref pose、短训、checkpoint 上传 | Completed，产出 `model_0.pt` / `model_20.pt` |
| motion reference DOF 顺序 | `TASK_20260611_007` / `f1_dh_stand` / 16 env / 5 iter | 验证 NPZ joint order 对齐 Isaac Gym DOF order | Completed，产出 `model_0.pt` / `model_5.pt` |
| motion imitation smoke | `TASK_20260611_032` / `f1_dh_motion_imitation` / 16 env / 5 iter | 验证 ref action 初始化、motion imitation reward 非零、云端可跑 | Completed，产出 `model_0.pt` / `model_5.pt` |
| 4096 env 正式训练 | `TASK_20260611_079` / 4096 env / 5000 iter | 按默认正式规模尝试长训 | Failed，`startTime=null`、`commitId=null`，没有进容器 |
| 1024 env 正式训练 | `TASK_20260612_003` / 1024 env / 5000 iter | 降低并行数后完成正式 motion imitation 长训 | Completed，产出 51 个云端 checkpoint，最终本地只保留 `model_5000.pt` |
| static stand / run-static 路线 | AutoDL `f1_run_static_stand` / model 3000 | 先训练稳定站立，再过渡到行走 | 有 rollout 视频/CSV，但 6 秒内 root_z 最低到 0.129m，尚未稳定 |

## 已做的核心代码与配置调整

### 1. MotionLoader 与 F1 DOF 对齐

早期重点是让重定向运动数据能被 F1 Isaac Gym 环境正确读取：

- `MotionLoader` 支持从 NPZ 读取 `dof_pos` / `dof_vel` / root pose / root velocity。
- 增加 DOF 顺序重排逻辑，避免 NPZ joint order 和 Isaac Gym asset DOF order 不一致。
- 支持可选 `foot_contacts` 字段，为后续 contact schedule reward 预留接口。

效果：

- `TASK_20260611_007` 验证通过，说明 DOF order 对齐后短训能正常启动并上传 checkpoint。

### 2. `f1_dh_motion_imitation` 奖励配置

新增或打开的 motion imitation 奖励包括：

- `ref_joint_pos`
- `motion_dof_vel`
- `motion_root_height`
- `motion_root_orientation`
- `motion_root_lin_vel`
- `motion_root_ang_vel`
- `motion_contact_schedule`，但早期 NPZ 没有 `foot_contacts`，所以权重为 0

同时降低或关闭原本偏 gait/command tracking 的启发式奖励：

- `feet_contact_number = 0.0`
- `feet_air_time = 0.0`
- `low_speed = 0.0`
- `track_vel_hard = 0.0`
- `tracking_lin_vel` / `tracking_ang_vel` 降低

思路：

直接用参考轨迹做模仿时，原先 command tracking、固定 gait timing、stand_still 等项可能和参考轨迹冲突。所以先让策略主要跟随参考关节、root 高度、root 姿态和 root 速度，再保留少量稳定性约束。

效果：

- `TASK_20260611_032` smoke test 中 motion reward 字段非零，证明 reward 接入是有效的。
- 但完整 5000 iteration 训练后，最终策略没有达到稳定行走，说明仅这些项还不足以解决初始稳定性和长时序模仿难度。

### 3. Reference action

`f1_dh_motion_imitation` 打开了：

```text
env.use_ref_actions = True
```

环境中维护 `ref_action`，将参考 DOF 位置相对当前 default pose 转成 action prior。其作用是让 policy 输出不是从零开始摸索，而是在参考动作附近学习残差。

曾经出现过一次问题：

```text
AttributeError: 'F1DHStandEnv' object has no attribute 'ref_action'
```

随后在 `_init_buffers` 中初始化 `self.ref_action`，再次提交后 smoke test 完成。

效果：

- 修复后 `TASK_20260611_032` 成功完成。
- 但 reference action 只能降低探索难度，不能单独解决姿态倒伏、接触时序、root 轨迹对齐等问题。

### 4. Root reset 与 root imitation

motion imitation 配置中打开：

```text
reset_root_orientation = True
reset_root_velocity = True
```

思路：

如果 reset 时 root 姿态/速度和参考轨迹不一致，策略一开始就要处理很大的状态偏差，容易早死。将 root 姿态和速度重置到参考可以减少初始不一致。

后续又加入或调整：

- `reset_root_height_offset`
- `align_ref_root_height_on_reset`
- `termination_min_base_height`
- `termination_max_ref_root_xy_distance`
- `termination_world_keypoint_thresholds`

效果：

- 对启动稳定性有帮助，但完整长轨迹中仍出现高度下降、早终止和倒伏倾向。

## 正式 5000 iteration 训练结果

### 4096 env 尝试

任务：

```text
TASK_20260611_079
gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_motion_imitation --headless --num_envs=4096 --max_iterations=5000
```

结果：

```text
taskStatus = 6
startTime = null
commitId = null
```

判断：

这不是训练代码运行时报错，而是平台没有真正进入容器启动/拉代码阶段。后续改为 1024 env。

### 1024 env 尝试

任务：

```text
TASK_20260612_003
gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_motion_imitation --headless --num_envs=1024 --max_iterations=5000
```

结果：

```text
taskStatus = 5 / Completed
startTime = 2026-06-12 09:02:50
endTime = 2026-06-12 13:46:20
runtime = 17010s, about 4h43m
commitId = a94b2a5949755cbee21886ceb73709dfb6613302
```

云端共上传 51 个 checkpoint，从 `model_0.pt` 到 `model_5000.pt`，间隔 100 iteration。按照后续约定，本地和 infer 目录只保留最终 checkpoint：

```text
cloud_artifacts/tasks/TASK_20260612_003/checkpoints/model_5000.pt
F:\Projects\agibot_x1_infer\training\TASK_20260612_003\checkpoints\model_5000.pt
```

最终模型：

```text
model_5000.pt
size = 14,776,578 bytes
sha256 = 6A943973BCA2D99EAFD8A2A146520D4E465912E24930BBBB117B958837B69CA6
```

日志尾部关键指标：

```text
Learning iteration 4999/5000
Mean reward: 0.00
Mean episode length: 36.78
Mean episode rew_action_smoothness: -0.7443
Mean episode rew_dof_torque_limits: -0.3261
Mean episode rew_dof_vel_limits: -0.0628
Mean episode rew_motion_root_height: 0.0053
Mean episode rew_motion_root_orientation: 0.0026
Mean episode rew_ref_joint_pos: -0.0043
RL task is successful.
```

判断：

训练流程成功，但策略质量不理想。`Mean episode length` 不高、`Mean reward` 接近 0，说明策略仍难以维持稳定长时序运动；动作平滑和 torque/dof limit 惩罚也比较显著。这个 checkpoint 更适合作为“能跑通的正式长训基线”，不是最终可部署策略。

## 后续 static stand / rephase / keypoint 路线

完整 walking motion 直接模仿太难后，路线调整为：

1. 先从稳定站立参考帧训练静态站立策略。
2. 再训练短片段或固定相位的 residual imitation。
3. 再打开 rephase motion、foot contacts、contact schedule 和更完整的行走片段。
4. 最后才扩展到完整 walking trajectory。

### 静态站立参考

新增 `doc/f1_static_stand_warmup_workflow.md`，核心思想是从：

```text
resources/motions/f1/v1.5/raw/motion_walk_0.6ms.csv
```

取第一帧生成静态 NPZ：

```text
resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0.npz
resources/motions/f1/v1.5/processed/motion_walk_0.6ms_static_stand_frame0_bodypos.npz
```

相关任务：

```text
f1_dh_static_stand
f1_run_static_stand
```

思路：

训练一开始就模仿完整行走，会同时遇到接触、root 速度、相位、姿态和动作残差问题。静态站立 warm-up 把问题拆小：先证明 policy 能让 F1 在参考姿态附近站住。

### World-space keypoint reward

后续代码引入了更强的空间关键点模仿：

- `ref_keypoint_pos`
- `motion_keypoint_pos_tokens`
- world-space body position diagnostics
- `termination_world_keypoint_thresholds`

思路：

单纯 joint angle imitation 不一定保证脚、膝、头、躯干在世界坐标里的位置合理，尤其 retarget 后关节角和实际接触几何之间可能有偏差。world-space keypoint reward 更直接约束身体部位位置。

### Rephase 与 contact schedule

新增/使用 rephase motion 数据：

```text
07_03_walk_yup_recwalk_base_lowerbody_smooth_p8_120_180_groundfit_minima_safe_rephase_stable_bodypos.npz
```

并支持生成/读取 `foot_contacts`，以便打开：

```text
motion_contact_schedule
```

思路：

让参考轨迹从更稳定的双支撑帧开始，避免 reset 到一个天然不稳定或接触状态不清晰的相位。contact schedule 则让策略学习“该接触时接触、该摆动时摆动”，减少脚滑和乱踩。

### 当前 static rollout 效果

已有本地 AutoDL snapshot：

```text
outputs/training_strategy_snapshot/autodl_model3000_20260623_123255/SNAPSHOT_INFO.txt
checkpoint=/root/autodl-tmp/f1_deploy/f1_train/logs/f1_run_static_stand/exported_data/2026-06-23_08-11-25f1_run_static_residual05_orient_resume500_12288env_to3000it_20260623_0805/model_3000.pt
```

本地 rollout 产物：

```text
outputs/policy_videos/f1_static_model3000_rollout_preview.gif
outputs/policy_videos/f1_static_model3000_rollout_600.mp4
outputs/policy_videos/f1_static_model3000_rollout_600.csv
outputs/policy_videos/f1_static_model3000_rollout_frame.png
```

CSV 量化结果：

```text
frames = 601
duration = 6.0s
root_z_start = 0.7743
root_z_end = 0.6140
root_z_min = 0.1290
root_z_max = 0.7749
root_x_drift = 0.2183
root_y_drift = 0.0573
```

判断：

`model_3000` 还不是稳定站立策略。6 秒内 root 高度最低到 0.129m，说明出现明显塌落/倒伏。这个阶段的价值主要是暴露问题：静态站立还没有解决，就不适合继续直接扩大到完整行走模仿。

## 目前最重要的经验

### 1. 先让环境和数据链路跑通，再谈策略质量

早期 smoke test 的价值很高。它们证明了：

- Gradmotion public GitHub 拉取可用。
- Isaac Gym 镜像可用。
- F1 29DOF task 可以注册和训练。
- motion NPZ 可以接入。
- checkpoint 能上传和下载。

这让后续问题可以聚焦到训练设计本身，而不是平台或代码启动问题。

### 2. 直接完整轨迹模仿过难

1024 env / 5000 iteration 的完成证明训练能跑，但最终表现不理想。这说明问题不是“训练没开始”，而是 imitation 目标和稳定性约束仍然不够好。

直接完整轨迹模仿同时要求：

- 关节角跟随。
- root 高度/姿态/速度跟随。
- 正确接触时序。
- 不倒、不穿地、不脚滑。
- 动作平滑、力矩不过限。

这些目标在早期训练阶段互相拉扯，容易得到“能优化一点 reward，但不能稳定站走”的策略。

### 3. contact schedule 不能长期缺席

早期 NPZ 没有 `foot_contacts`，所以 `motion_contact_schedule` 只能设为 0。对于行走模仿，这是一个明显缺口。

后续 rephase motion 中加入 `foot_contacts` 是必要方向。没有接触监督时，策略可能在 root/joint reward 上做局部优化，但脚底接触状态仍然不对。

### 4. 空间关键点比纯关节角更直观

对于 humanoid retarget，纯 joint angle 不一定能保证身体实际空间姿态正确。world-space keypoint reward 和 body position diagnostics 更适合诊断：

- 脚是否在合理高度。
- 膝/踝相对身体是否正常。
- 头/neck 是否偏离过大。
- root 是否因为局部关节匹配而整体倒伏。

### 5. static stand 是必要前置关卡

当前 static rollout 仍然倒伏，说明基础站立控制还没过关。后续不应急着扩大到完整 walking；应先让 static stand 训练达到：

- 6 秒以上 root 高度不明显塌落。
- root xy drift 小。
- 无明显 base contact / fall termination。
- 关节和关键点误差可控。

## 后续建议

### 短期

1. 继续优先调 `f1_run_static_stand` / `f1_dh_static_stand`，不要直接重跑完整 walking imitation。
2. 用小 batch GUI 先确认初始姿态、脚底接触、root 高度和终止原因，再开大规模 headless。
3. 对 static stand 增强 root height / orientation / world keypoint 约束，但避免过强 action/torque 惩罚把 policy 压死。
4. 保留 rollout CSV + 视频作为每轮对比标准，不只看训练 reward。

### 中期

1. static stand 稳定后，使用 rephase stable motion，从固定相位或短片段开始。
2. 打开 `motion_contact_schedule`，前提是参考 NPZ 有可靠 `foot_contacts`。
3. 逐步增加 playback speed 和 phase randomization，而不是一开始全随机相位。
4. 逐步从静态站立扩展到 0.5-1.0 秒短片段，再到完整循环。

### 产物管理

1. 云端完成任务后继续下载：

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\download-task-artifacts.ps1 -TaskId TASK_xxx
```

2. 默认只保留最新 checkpoint，避免中间模型占用过多磁盘。
3. 训练产物同步到：

```text
F:\Projects\agibot_x1_infer\training\<TASK_ID>\
```

## 当前可引用产物

云端正式训练：

```text
cloud_artifacts/tasks/TASK_20260612_003/
F:\Projects\agibot_x1_infer\training\TASK_20260612_003\
```

最终模型：

```text
cloud_artifacts/tasks/TASK_20260612_003/checkpoints/model_5000.pt
```

static rollout 诊断：

```text
outputs/policy_videos/f1_static_model3000_rollout_preview.gif
outputs/policy_videos/f1_static_model3000_rollout_600.mp4
outputs/policy_videos/f1_static_model3000_rollout_600.csv
```

static warm-up 工作流：

```text
doc/f1_static_stand_warmup_workflow.md
```

