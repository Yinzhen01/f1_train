# Codex 操作 Gradmotion 云桌面的最小复现流程

本文是快速清单，用于在新 Gradmotion GUI 云桌面上复现：

```text
Codex 通过 SSH 操作云桌面
用户在云桌面侧能看到 Codex 打开的 GUI 窗口
```

完整解释、原理和排错见：

```text
doc/gradmotion_reverse_ssh_gui_workflow.md
```

## 固定前提

需要一台有公网 IP 的跳板机，例如阿里云 ECS。

跳板机需要满足：

```text
SSH 可登录
安全组放行反向端口，例如 2222
sshd 允许 TCP 转发
如果 Codex 要从公网直连该端口，需要允许 GatewayPorts
```

Codex 本地需要有一把专用于 Gradmotion 的 SSH 私钥，并与仓库里的公钥文件匹配：

```text
ops/gradmotion/codex_gradmotion.pub
```

仓库里只提交公钥，绝不提交私钥。

## 最短流程

新申请一台 Gradmotion GUI 云桌面后，先 clone 项目，然后执行：

```bash
cd /root/limx_rl/f1_train
git pull
bash ops/gradmotion/start-codex-tunnel.sh
```

这个脚本会依次完成：

```text
把 ops/gradmotion/codex_gradmotion.pub 加入 /root/.ssh/authorized_keys
检查 Gradmotion 本机 sshd 是否监听 22 端口
运行 ops/gradmotion/bootstrap-gui-desktop.sh 完成环境安装和 viewer smoke test
连接固定 ECS 跳板机，并保持反向 SSH 隧道
```

脚本最后会停在前台保持隧道。不要关闭该终端。此时 Codex 可以通过固定 ECS 和反向端口连入这台 Gradmotion。

如果有多台 Gradmotion 同时在线，每台使用不同端口：

```bash
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2222
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2223
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2224
```

如果只想先打通 SSH，不跑环境部署和 viewer smoke test：

```bash
bash ops/gradmotion/start-codex-tunnel.sh --no-bootstrap
```

云桌面重启后，如果项目和 Python 环境还在，优先走这个最快恢复流程：

```bash
cd /root/limx_rl/f1_train
git pull
bash ops/gradmotion/start-codex-tunnel.sh --no-bootstrap
```

脚本提示 `root@121.40.166.191's password:` 时，在云桌面终端里输入 ECS root 密码。输入后终端停住是正常状态，表示反向隧道正在保持。不要关闭这个终端。

如果想减少 smoke test 时间，可以把参数传给 bootstrap：

```bash
bash ops/gradmotion/start-codex-tunnel.sh -- --skip-gui-smoke
```

## 每次新机器都要重新做的事

这些内容通常是一次性的，不要假定下次还一样：

```text
Gradmotion hostname
Gradmotion GUI 用户名
DISPLAY 值
XAUTHORITY 路径
反向 SSH 隧道进程
云桌面登录 Token 或控制台链接
```

## 1. 在 Gradmotion 确认 SSH 服务

在 Gradmotion 云桌面终端执行：

```bash
ss -lntp | grep ':22'
systemctl status ssh || service ssh status
```

如果看到 `0.0.0.0:22` 或 `[::]:22` 监听，说明云桌面本机 SSH 服务可用。

## 2. 给 Gradmotion 加 Codex 临时公钥

在 Gradmotion 云桌面执行：

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
```

追加 Codex 本地临时 key 的 `.pub` 公钥：

```bash
cat >> /root/.ssh/authorized_keys <<'EOF'
<粘贴 Codex 临时 .pub 公钥的单行内容>
EOF
chmod 600 /root/.ssh/authorized_keys
```

不要把私钥复制到 Gradmotion，也不要写入仓库。

## 3. 在 Gradmotion 开反向 SSH 隧道

在 Gradmotion 云桌面终端执行，并保持该终端不要关闭：

```bash
ssh -N -R 2222:localhost:22 root@<ECS_PUBLIC_IP>
```

第一次连接时输入：

```text
yes
```

然后输入 ECS 登录密码或使用 ECS 已配置的登录 key。

输入密码后终端没有新输出是正常的。`-N` 表示只保持隧道，不打开远程 shell。

## 4. 在 ECS 上确认反向端口

在 ECS 上执行：

```bash
ss -lntp | grep 2222
```

期望看到类似：

```text
LISTEN 0 128 0.0.0.0:2222 0.0.0.0:* users:(("sshd",...))
```

如果没有监听，说明第 3 步隧道没有建立成功或已经断开。

## 5. Codex 本地测试 SSH 链路

在 Codex 本地机器执行：

```powershell
ssh -i <本机临时私钥路径> -p 2222 root@<ECS_PUBLIC_IP> "hostname && pwd && echo tunnel-login-ok"
```

看到 Gradmotion 的 hostname 和 `tunnel-login-ok`，说明 Codex 已经能通过 ECS 反连到 Gradmotion。

## 6. 在 Gradmotion 项目里探测 GUI 环境

Codex 通过 SSH 进入 Gradmotion 后执行：

```bash
cd /root/limx_rl/f1_train
bash ops/gradmotion/gui-desktop-train.sh gui-env
```

脚本会探测：

```text
GUI_USER
DISPLAY
XAUTHORITY
/tmp/.X11-unix
```

如果自动探测不准，手动查看：

```bash
who
ls -la /tmp/.X11-unix
ps -ef | egrep 'Xorg|gnome-shell|Xwayland'
```

常见组合是：

```text
DISPLAY=:1
XAUTHORITY=/home/<GUI_USER>/.Xauthority
```

## 7. 打开一个 GUI 小窗口

优先使用项目脚本：

```bash
bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

如果用户在云桌面里能看到 `xclock`，说明 GUI 显示链路可用。

如果看不到，手动指定 GUI 参数：

```bash
GUI_USER=<GUI_USER> DISPLAY=:1 XAUTHORITY=/home/<GUI_USER>/.Xauthority \
  bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

## 8. 跑 Isaac Gym viewer smoke test

用户确认能看到 GUI 窗口后，再运行：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-single
bash ops/gradmotion/gui-desktop-train.sh gui-smoke
```

如果目标是让用户在云桌面里持续观察 Isaac Gym viewer，不要让 viewer 依赖当前 SSH 会话，使用后台保持模式：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-hold
```

默认参数：

```text
NUM_ENVS=1
MAX_ITERATIONS=100000
RUN_NAME=codex_gui_viewer_hold
日志: /tmp/codex_isaac_viewer_hold.log
PID: /tmp/codex_isaac_viewer_hold.pid
```

查看后台 viewer 状态：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-hold-status
```

关闭后台 viewer：

```bash
bash ops/gradmotion/gui-desktop-train.sh stop-gui-hold
```

本次已验证的 10 环境可视训练模板：

```bash
cd /root/limx_rl/f1_train
NUM_ENVS=10 MAX_ITERATIONS=100000 RUN_NAME=f1_gui_10env_YYYYMMDD \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold
```

如果目标是基于 F1 29DOF 重定向数据做动作模仿训练，优先选择 motion imitation 入口，而不是普通 `f1_dh_stand`：

```bash
cd /root/limx_rl/f1_train
TASK=f1_dh_motion_imitation NUM_ENVS=10 MAX_ITERATIONS=100000 \
  RUN_NAME=f1_motion_imitation_gui_10env_YYYYMMDD \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

`gui-hold-focused` 会在环境创建后读取 `env.env_origins[VIEWER_FOCUS_ENV]`，再把 viewer 相机对准该环境。默认聚焦第一个机器人：

```text
VIEWER_FOCUS_ENV=0
VIEWER_REL_POS=1.3,-1.2,1.1
VIEWER_REL_LOOKAT=0,0,0.75
```

如果机器人仍然太小，可以继续拉近：

```bash
TASK=f1_dh_motion_imitation NUM_ENVS=10 MAX_ITERATIONS=100000 \
  RUN_NAME=f1_motion_imitation_gui_close_YYYYMMDD \
  VIEWER_REL_POS=0.9,-0.8,0.9 VIEWER_REL_LOOKAT=0,0,0.7 \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

启动日志会明确打印以下信息，用来判断是否真的跑在 29DOF 重定向模仿入口上：

```text
task: f1_dh_motion_imitation
asset: {LEGGED_GYM_ROOT_DIR}/resources/robots/f1_v1.5/urdf/F1_29DOF_physically_mirrored.urdf
num_actions: 29
motion_reference.enabled: True
motion_reference.file: resources/motions/f1/v1.5/processed/...groundfit_minima_safe.npz
env.use_ref_actions: True
reward_scale.motion_root_height / orientation / lin_vel / ang_vel: non-empty
```

用于摔倒和偏离重定向轨迹的可视化诊断参数：

```bash
TASK=f1_dh_motion_imitation NUM_ENVS=10 MAX_ITERATIONS=100000 \
  RUN_NAME=f1_motion_imitation_debug_YYYYMMDD \
  TERRAIN_MESH_TYPE=plane \
  TERMINATION_MIN_BASE_HEIGHT=0.40 \
  TERMINATION_MAX_REF_ROOT_XY_DISTANCE=0.5 \
  TERMINATION_SUPPORT_RECT_MARGIN=0.10 \
  JOINT_DIAG_INTERVAL=50 JOINT_DIAG_TOPK=12 TERMINATION_DIAG_INTERVAL=50 \
  VIEWER_REL_POS=1.0,-0.85,0.85 VIEWER_REL_LOOKAT=0,0,0.65 \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

其中 `TERMINATION_MAX_REF_ROOT_XY_DISTANCE` 比较的是 reset 时刻对齐后的 motion root XY 偏离量，不是 NPZ 里的绝对 root XY 坐标。不要直接用未对齐的 `ref_root_pos[:, :2]` 和仿真世界坐标比较，否则 motion 文件自带的全局位移会导致环境一开始就被判定失败。

motion imitation 默认保留小权重的逐关节角度位置奖励作为辅助姿态先验，但不把它作为主要模仿约束，也不默认使用逐关节角度误差做硬 reset。后续应优先使用 body/keypoint 的空间位置误差来约束重定向动作；`TERMINATION_SUPPORT_RECT_MARGIN` 会在质量加权 CoM 的 XY 越出双脚当前位置构成的轴对齐矩形时提前 reset，单位是米，例如 `0.10` 表示允许越出双脚矩形 10cm。

使用自定义 `RUN_NAME` 后，查看状态和关闭时也要带同一个 `RUN_NAME`：

```bash
RUN_NAME=f1_gui_10env_YYYYMMDD bash ops/gradmotion/gui-desktop-train.sh gui-hold-status
RUN_NAME=f1_gui_10env_YYYYMMDD bash ops/gradmotion/gui-desktop-train.sh stop-gui-hold
```

后台 viewer 日志固定写入：

```text
/tmp/codex_isaac_viewer_hold.log
```

训练产物仍写入：

```text
logs/f1_dh_stand/exported_data/<timestamp><RUN_NAME>/
```

当前默认 viewer 相机来自：

```text
humanoid/envs/base/legged_robot_config.py
viewer.pos = [10, 0, 6]
viewer.lookat = [11., 5, 3.]
```

这个视角适合先看 10 个环境的整体场景；如果想看清单个机器人，可以在 Isaac Gym viewer 里拖动/缩放，或后续调整 `viewer.pos/lookat` 后重启 viewer。

如果是新机器完整部署，优先运行：

```bash
bash ops/gradmotion/bootstrap-gui-desktop.sh
```

该脚本默认只执行安装、环境检查和 viewer smoke test，不会启动正式长训练。

正式训练需要用户明确要求后再执行：

```bash
RUN_NAME=f1_29dof_v1 bash ops/gradmotion/bootstrap-gui-desktop.sh --train
```

## 9. 会话结束清理

停止反向隧道：

```text
回到 Gradmotion 上运行 ssh -N -R 的终端，按 Ctrl-C。
```

删除临时公钥：

```bash
sed -i '/codex-gradmotion/d' /root/.ssh/authorized_keys
```

如果本次没有使用带 `codex-gradmotion` 标记的公钥注释，不要直接运行上面的命令，先人工确认要删的公钥行。

## 10. 快速判断问题位置

```text
ECS 上看不到 2222 监听
  反向隧道没有建立或已经断开。

Codex 连接 2222 超时
  ECS 安全组、GatewayPorts 或公网访问路径有问题。

Codex 连接 Permission denied
  Gradmotion authorized_keys 没有对应公钥，或私钥不匹配。

xclock 进程存在但用户看不到窗口
  DISPLAY 或 XAUTHORITY 不属于当前云桌面 GUI 会话。

Isaac Gym viewer 起不来，但 xclock 可见
  优先排查 Isaac Gym、GPU、Python 环境和训练脚本参数。
```
