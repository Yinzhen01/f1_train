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
