# Codex 操作 Gradmotion GUI 云桌面的原理与方式

本文解释 Codex 之前通过 Gradmotion GUI 云桌面进行可视化训练、调试和进程管理的整体原理。最小复现步骤见：

```text
doc/gradmotion_codex_gui_minimal_repro.md
```

逐步命令和排错细节见：

```text
doc/gradmotion_reverse_ssh_gui_workflow.md
```

## 目标

目标不是让 GUI 窗口显示在 Codex 本地机器上，而是：

```text
Codex 通过 SSH 操作 Gradmotion 云桌面
用户在 Gradmotion 云桌面那边直接看到 Codex 打开的窗口
```

因此 Isaac Gym viewer、xclock、日志窗口等 GUI 程序都运行在 Gradmotion 云桌面本机，并显示在该云桌面当前图形会话里。Codex 只负责通过 SSH 下命令、启动程序、读取日志、停止进程、调整脚本。

## 总体链路

Gradmotion GUI 云桌面通常没有可从公网直接访问的 SSH 地址，所以使用一台有公网 IP 的 ECS 作为跳板机。

```text
Codex 本地机器
  -> ssh -p <REMOTE_PORT> root@<ECS_PUBLIC_IP>
  -> 连接到 ECS 上的反向端口
  -> 实际进入 Gradmotion 云桌面的 localhost:22

Gradmotion GUI 云桌面
  -> 主动 ssh 到 ECS
  -> ssh -N -R <REMOTE_PORT>:localhost:22 root@<ECS_PUBLIC_IP>
  -> 把自己的 SSH 服务反向映射到 ECS

用户
  -> 通过 Gradmotion/无影云桌面客户端或网页看 GUI 桌面
```

核心点是：Gradmotion 主动连出去建立反向 SSH 隧道。只要隧道终端不断开，Codex 就可以通过 ECS 的反向端口登录 Gradmotion。

## 为什么用户能看到 Codex 打开的 GUI

Codex 通过 SSH 登录 Gradmotion 后，默认进入的是 root shell。这个 shell 本身不是图形桌面会话，所以直接运行 GUI 程序可能出现：

```text
进程存在，但用户看不到窗口
```

要让窗口显示在用户正在看的云桌面里，需要把 GUI 程序放到正确的 X11 会话中，关键变量是：

```text
DISPLAY
XAUTHORITY
GUI_USER
```

常见组合类似：

```text
DISPLAY=:1
GUI_USER=gm_xxxxx
XAUTHORITY=/home/gm_xxxxx/.Xauthority
```

项目脚本 `ops/gradmotion/gui-desktop-train.sh` 会尽量自动探测这些值。验证命令：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-env
bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

如果 `xclock` 能出现在用户正在看的云桌面上，说明 Codex 启动 GUI 程序的显示链路是通的。

## 一键入口

新 Gradmotion GUI 云桌面已经 clone 项目后，优先使用：

```bash
cd /root/limx_rl/f1_train
git pull
bash ops/gradmotion/start-codex-tunnel.sh
```

这个脚本负责：

```text
安装或检查训练环境
检查 SSH 服务
添加 Codex 公钥
运行 GUI/Isaac Gym smoke test
连接固定 ECS 跳板机
保持反向 SSH 隧道
```

如果云桌面只是重启过，项目和 Python 环境还在，可用更快入口：

```bash
cd /root/limx_rl/f1_train
git pull
bash ops/gradmotion/start-codex-tunnel.sh --no-bootstrap
```

当终端停在类似下面的提示后，输入 ECS root 密码：

```text
root@<ECS_PUBLIC_IP>'s password:
```

输入后终端没有新输出是正常的，因为 `ssh -N` 只保持隧道，不打开远程 shell。这个终端必须保持打开。

## Codex 侧如何连接

隧道建立后，Codex 本地通过 ECS 的反向端口登录 Gradmotion：

```powershell
ssh -i "$env:USERPROFILE\.ssh\codex_gradmotion_ed25519" `
  -p 2222 `
  root@<ECS_PUBLIC_IP> `
  "hostname && pwd && echo tunnel-login-ok"
```

如果输出的是 Gradmotion 云桌面的 hostname，并看到：

```text
tunnel-login-ok
```

说明 Codex 已经能够操作 Gradmotion。

本项目当前常用的连接形态是：

```text
ECS 公网 IP: 121.40.166.191
默认反向端口: 2222
Gradmotion 项目目录: /root/limx_rl/f1_train
```

不要把 ECS 密码、云桌面登录 token、签名 URL、私钥写入仓库或聊天记录。

## 启动可视化训练

小批量 GUI 检查优先使用：

```bash
TASK=f1_dh_static_stand NUM_ENVS=10 MAX_ITERATIONS=100000 \
  RUN_NAME=f1_static_stand_gui_10env_YYYYMMDD \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

`gui-hold-focused` 会使用 `train_focused_view.py`，并把 Isaac Gym viewer 相机对准指定环境，便于用户观察第一个机器人：

```text
VIEWER_FOCUS_ENV=0
VIEWER_REL_POS=1.3,-1.2,1.1
VIEWER_REL_LOOKAT=0,0,0.75
```

需要拉近视角时，可以覆盖相机参数：

```bash
VIEWER_REL_POS=0.9,-0.8,0.9 VIEWER_REL_LOOKAT=0,0,0.7 \
  bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
```

## 后台运行的含义

长时间保留 viewer 或训练时，不建议把 Python 进程直接挂在当前 SSH 前台命令里。更稳的方式是后台启动：

```text
nohup + 后台进程 + 日志文件 + PID 文件
```

这样即使 Codex 这边 SSH 命令结束，Gradmotion 上的 Isaac Gym viewer 或训练进程仍可继续运行。

项目脚本已经封装了 viewer 后台保活：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-hold-status
bash ops/gradmotion/gui-desktop-train.sh stop-gui-hold
```

正式 headless 训练也应使用类似方式保活，并把日志写到 `/tmp/<run_name>.log` 或项目约定的日志目录。之后 Codex 通过 SSH 读取日志和 `nvidia-smi` 判断训练状态。

## 正式训练与 GUI 检查的关系

推荐顺序是：

```text
先小批量 GUI 检查
确认参考动作、初始姿态、相机视角、死亡原因观测方式
再启动大批量 headless 正式训练
```

GUI 小批量的价值是让用户直接看到：

```text
机器人初始姿态是否匹配参考数据
是否有明显弹起、滑步、侧倒
红色参考关键点是否和机器人关键点对齐
死亡瞬间是否肉眼可解释
```

headless 正式训练的价值是高吞吐。它不能替代 GUI 验证，尤其在处理重定向数据、关键点奖励、死亡条件和接触问题时。

## 多台 Gradmotion 同时管理

可以同时管理多台 Gradmotion 云桌面，但每台需要不同的反向端口：

```bash
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2222
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2223
bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2224
```

Codex 连接时根据端口区分机器：

```powershell
ssh -p 2222 root@<ECS_PUBLIC_IP> "hostname"
ssh -p 2223 root@<ECS_PUBLIC_IP> "hostname"
ssh -p 2224 root@<ECS_PUBLIC_IP> "hostname"
```

多机管理时建议记录：

```text
端口
Gradmotion hostname
项目目录
当前 run_name
训练 PID
日志路径
GPU 型号和显存
```

不要只靠“这台/那台”这样的口头描述，否则很容易把命令发到错误机器。

## 常见问题判断

### 输入 ECS 密码后终端像卡住

正常。`ssh -N -R ...` 的作用就是保持隧道，不输出 shell。

### Codex 连不上 2222

先在 ECS 上检查：

```bash
ss -lntp | grep 2222
```

如果没有监听，说明 Gradmotion 到 ECS 的反向隧道没有建立或已经断开。

### 程序启动了但用户看不到窗口

通常是 `DISPLAY` 或 `XAUTHORITY` 不对。先跑：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-env
bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

确认 `xclock` 能被用户看到后，再启动 Isaac Gym viewer。

### Isaac Gym 窗口被 Codex 命令结束带着关掉

说明 viewer 依赖当前 SSH 前台进程。改用 `gui-hold` 或 `gui-hold-focused` 后台方式。

### 训练还在但 SSH 命令超时

如果训练用 `nohup` 后台启动，SSH 超时不一定代表训练失败。用下面命令确认：

```bash
pgrep -af 'train_focused_view.py|humanoid/scripts/train.py'
nvidia-smi
tail -n 120 /tmp/<run_name>.log
```

## 安全与清理

仓库只允许保存公钥，不允许保存：

```text
私钥
密码
登录 token
签名 URL
云桌面控制台一次性链接
训练平台充值或账户敏感记录
```

会话结束后，如果使用的是临时 key，应从 Gradmotion 删除对应公钥行：

```bash
vim /root/.ssh/authorized_keys
```

如果不再需要该云桌面被 Codex 操作，关闭保持反向隧道的终端即可。
