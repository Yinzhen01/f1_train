# F1 跑步/站立预训练问题、调整与效果复盘

本文整理本轮 F1 29DOF 基于重定向数据训练过程中遇到的问题、对应调整思路、已观察到的效果，以及后续建议。目标是把“为什么这么改”和“改完到底有没有变好”记录清楚，便于后续继续训练或切换到动态跑步模仿。

## 当前结论

截至 `model_3000.pt`，策略相比早期已经有明显改善，但还不能认为可用：

- 训练统计在 `3000 iter` 时已出现较高超时比例，说明部分 episode 可以撑满时长。
- 可视化推理显示仍会摔倒：导出的 6 秒视频中，第一段 episode 约 `2.45s` 摔倒并触发 reset，后半段是 reset 后的新 episode。
- 因此当前 checkpoint 不能作为稳定站立/跑步策略使用，只能作为继续训练和调参的中间结果。

当前已启动从 `model_3000.pt` 续训到 `5000 iter` 的实验。早期日志显示指标仍在波动，需等 `model_5000.pt` 后再做诚实推理评估。

## 主要问题

### 1. 直接做动态模仿太难

最初希望直接基于重定向走/跑数据进行模仿，但参考动作本身包含动态单支撑、根姿态变化、足端接触切换等因素。F1 初始控制策略还没有稳态站立能力时，直接学习全动态动作容易出现：

- 初始几百毫秒内侧倒或前后倒。
- reward 在早期长时间无明显提升。
- episode 过短，策略难以覆盖有效状态空间。

### 2. actor 输入信息不足

与同事策略相比，原策略的关键差距之一是 actor 是否直接看到参考动作相关信息。

本轮调整前的核心问题是：网络可以通过 reward 被动知道“做错了”，但 actor 观测里没有足够直接的信息告诉它“当前相位应该朝哪个参考姿态修正”。这会把问题变成盲目试错。

因此后续采用：

```text
target_dof_pos = ref_dof_pos(t) + action * action_scale
```

也就是 residual PD imitation。网络输出的是相对于当前参考帧的残差，而不是从默认站姿出发重新生成完整动作。

### 3. 参考数据起始相位不稳定

动态重定向数据如果从单支撑或身体偏斜相位开始，reset 后机器人很容易立即倒。即使 reward 正确，策略也可能长期学不到稳定起点。

因此训练流程从“完整动态动作”退一步，先做固定相位、静态参考的站立 warm-up。

### 4. 终止条件和奖励目标互相拉扯

训练中多次出现“刚开始就被终止”或“策略为了拿短期 imitation reward 而牺牲稳定”的现象。典型表现包括：

- `termination_height_rate` 高：身体高度掉到阈值以下。
- `termination_roll_rate` 高：身体 roll 角过大。
- base contact 过早终止导致策略没有恢复机会。

这些现象说明奖励和终止条件需要按阶段放松或强化，而不是一开始就使用完整动态模仿的严格判定。

## 关键调整

| 阶段 | 调整 | 思路 | 观察到的效果 |
| --- | --- | --- | --- |
| actor/动作接口 | 启用 `use_ref_actions=True` 和 `use_ref_dof_pos_observation=True` | 让 actor 直接看到参考姿态相关信息，动作输出只学残差 | 学习问题从“生成完整动作”变成“修正参考动作”，难度显著下降 |
| 控制目标 | 使用 `ref(t) + action * scale` 残差 PD | 参考动作负责主轨迹，policy 只负责补偿仿真误差和稳定性 | 比相对默认姿态输出更适合模仿任务 |
| 课程 | 增加 `f1_run_static_stand` | 在进入走/跑模仿前，先训练与跑步接口兼容的站立 warm-up | 能训练出部分可存活 episode，但 `model_3000.pt` 仍会摔 |
| 参考相位 | 使用 rephase stable motion，并固定 `randomize_start_phase=False` | 避免从动态单支撑相位 reset，减少早期倒地 | 初始姿态更可控，便于诊断 |
| 参考播放 | `playback_speed=0.0` | 把动态参考冻结成静态目标，先解决站稳 | 把任务从动态 tracking 降为静态 imitation/stability |
| 根状态 reset | `reset_root_orientation=True`、`reset_root_velocity=True` | reset 时根姿态/速度与参考一致，减少起步瞬间冲击 | 初始状态更一致 |
| 高度处理 | `reset_root_height_offset=0.15`，`align_ref_root_height_on_reset=False` | 给站立参考额外离地余量，避免初始穿地或腿部压缩 | 初始高度更安全，但后续仍需控制住姿态 |
| 终止条件 | `terminate_after_contacts_on=[]`，`termination_min_base_height=0.12` | 早期放松 base contact 和高度终止，让策略有恢复机会 | 避免过早结束，但也可能允许摔倒片段持续更久 |
| 奖励强化 | 增大 `motion_root_orientation=12.0`、`orientation=2.0` | 更强地惩罚姿态偏离，压 roll/pitch 失稳 | 训练后 roll 问题仍存在，但比早期可诊断 |
| 动作幅度 | `action_scale=0.5`，`init_noise_std=0.45` | 给残差足够调节空间，同时保留探索 | 残差平均值较高但未饱和，说明策略仍在用动作补偿 |
| 规模 | 使用 `12288 env` | 48GB GPU 下提高采样吞吐，减少长时间无趋势的问题 | 训练速度约 `4.3-6.3s/iter`，采样效率可接受 |
| 可视化 | 从 Isaac Gym camera 改为 policy rollout CSV + MuJoCo 离线渲染 | AutoDL 无显示环境下 Isaac Gym camera 会崩溃，离线渲染更稳定 | 已生成 MP4/GIF，并暴露出 `model_3000.pt` 仍摔倒的问题 |

## 当前配置重点

主要训练任务：

```text
f1_run_static_stand
```

注册位置：

```text
humanoid/envs/__init__.py
```

核心配置：

```text
humanoid/envs/f1/f1_dh_stand_config.py
```

关键设置摘要：

```text
class F1RunStaticStandCfg(F1RunCfg):
    asset.terminate_after_contacts_on = []
    control.action_scale = 0.5
    motion_reference.playback_speed = 0.0
    motion_reference.randomize_start_phase = False
    motion_reference.reset_root_height_offset = 0.15
    motion_reference.align_ref_root_height_on_reset = False
    rewards.termination_min_base_height = 0.12
    rewards.scales.motion_root_orientation = 12.0
    rewards.scales.orientation = 2.0
    rewards.scales.yaw_penalty = -0.5

class F1RunStaticStandCfgPPO(F1RunCfgPPO):
    policy.init_noise_std = 0.45
    runner.experiment_name = "f1_run_static_stand"
```

当前使用的参考文件：

```text
resources/motions/f1/v1.5/processed/07_03_walk_yup_recwalk_base_lowerbody_smooth_p8_120_180_groundfit_minima_safe_rephase_stable_bodypos.npz
```

## 训练效果记录

### 到 `3000 iter`

最终训练日志的关键指标：

```text
Mean reward: 737.92
Mean episode length: 1991.96
termination_timeout_rate: 0.7580
termination_height_rate: 0.1144
termination_roll_rate: 0.1230
base_height_reset_mean: 0.5140
Total timesteps: 737280000
```

这些指标说明：训练中已有大量 episode 可以撑到 timeout，但仍存在高度和 roll 终止。

### `model_3000.pt` 推理可视化

可视化文件：

```text
outputs/policy_videos/f1_static_model3000_rollout_600.mp4
outputs/policy_videos/f1_static_model3000_rollout_preview.gif
outputs/policy_videos/f1_static_model3000_rollout_600.csv
```

CSV 量化结果：

```text
0.00s: base height ~= 0.774m
2.23s: base height < 0.45m
2.39s: base height < 0.25m
2.45s: min height ~= 0.129m, roll ~= 35deg, pitch ~= 48deg
2.50s: episode reset 后重新站起
```

结论：`model_3000.pt` 的视频中不是稳定站立 6 秒，而是包含摔倒后 reset 的新 episode。因此推理视频必须支持 `stop_on_done` 或 reset 标记，否则容易误判策略质量。

### 续训到 `5000 iter` 的早期趋势

已从 `model_3000.pt` 继续训练：

```text
load_run: 2026-06-23_08-11-25f1_run_static_residual05_orient_resume500_12288env_to3000it_20260623_0805
checkpoint: model_3000.pt
num_envs: 12288
max_iterations: 2000
target final checkpoint: model_5000.pt
```

注意：本代码中 `--max_iterations` 表示“本次再训练多少 iter”。从 `iter=3000` 到 `iter=5000`，因此传 `2000`。

截至日志约 `3096/4999`：

```text
Mean reward: 552.90
Mean episode length: 1603.67
termination_height_rate: 0.5208
termination_roll_rate: 0.5000
```

这个阶段仍处于波动期，不能作为最终结论。早期从 `3014` 到 `3060` 曾看到 episode length 从约 `337` 回升到约 `1128`，说明继续训练仍有恢复趋势，但 `height/roll` 终止尚未解决。

## 对问题的判断

### 继续训练是否有价值

有价值，但需要设观察窗口。理由：

- `model_3000.pt` 不是一开始就炸，而是在约 `2.45s` 才倒，说明策略已有部分稳定能力。
- 训练指标中 timeout episode 已经出现较高比例，说明不是完全无效策略。
- 续训早期指标有回升迹象。

但如果到 `5000 iter` 后 honest eval 仍在几秒内摔倒，就不应继续单纯堆训练步数，而应调整奖励/终止/课程。

### 当前最大风险

1. **训练指标和真实推理视频不一致。**  
   训练统计是多环境平均，且 episode reset 后继续采样；单条视频如果不标记 done，会把多个 episode 拼在一起。

2. **过度放松终止可能掩盖失败。**  
   `termination_min_base_height=0.12` 和取消 base contact 终止让策略有恢复机会，但也允许明显摔倒片段进入采样。

3. **roll/height 失败仍是主问题。**  
   当前 failure 主要不是关节跟踪误差，而是身体高度和姿态稳定性。

4. **静态站立还没完全解决，不宜急着切动态跑步。**  
   在站立 warm-up 仍摔倒时切换动态参考，会把问题复杂度再次放大。

## 下一步建议

### 1. 完成 `5000 iter` 后做 honest eval

推理可视化必须支持：

```text
stop_on_done = True
```

或者至少在视频/CSV 中标注 reset 时间点。评估指标应包括：

```text
平均存活时间
timeout 比例
height termination 比例
roll termination 比例
pitch termination 比例
单条最长无 reset 推理视频
```

### 2. 如果 `5000 iter` 后仍摔倒

优先考虑这些调整：

- 提高 `termination_min_base_height`，不要让明显趴地还继续采样。
- 保留 base contact 诊断，但不要立刻硬终止所有 base contact；可以先做惩罚项。
- 强化 roll/pitch 姿态稳定项，尤其是早期 episode。
- 降低 `action_scale` 或 `init_noise_std`，检查残差动作是否过大导致自激。
- 做更短的阶段课程：先纯站立，再轻微相位扰动，再低速动态。

### 3. 不建议立即进入完整跑步模仿

当前最稳妥的路线仍然是：

```text
静态站立稳定
-> 固定相位短片段
-> 小范围相位随机
-> 低速走路/跑步片段
-> 完整动态参考
```

只有当 honest eval 中站立 checkpoint 能稳定无 reset 存活较长时间，才值得切到动态参考。

## 相关产物

训练策略快照：

```text
outputs/training_strategy_snapshot/autodl_model3000_20260623_123255/
```

推理可视化结果：

```text
outputs/policy_videos/f1_static_model3000_rollout_600.mp4
outputs/policy_videos/f1_static_model3000_rollout_preview.gif
outputs/policy_videos/f1_static_model3000_rollout_600.csv
```

新增/修改的辅助脚本：

```text
humanoid/scripts/record_policy_rollout_csv.py
humanoid/scripts/render_motion_mujoco.py
```

远端续训日志：

```text
/root/autodl-tmp/f1_deploy/run_logs/train_to5000_20260623_1238.out
```

