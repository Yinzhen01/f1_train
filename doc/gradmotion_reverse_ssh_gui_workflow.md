# Gradmotion 云桌面反向 SSH 与 GUI 显示流程

本文记录一种可复用流程：Codex 在本地通过一台有公网 IP 的跳板机连接 Gradmotion GUI 云桌面，并且启动的 GUI 程序显示在用户正在看的云桌面上。

如果只需要在新机器上快速复现，优先使用最小清单：

```text
doc/gradmotion_codex_gui_minimal_repro.md
```

在新 Gradmotion GUI 云桌面 clone 项目后，推荐入口是：

```bash
cd /root/limx_rl/f1_train
git pull
bash ops/gradmotion/start-codex-tunnel.sh
```

适用场景：

- Gradmotion 云桌面本身没有可直接公网 SSH 的地址。
- 用户可以在浏览器或云桌面客户端看到 Gradmotion 图形界面。
- Codex 需要通过 SSH 执行命令、启动训练、打开 Isaac Gym viewer。
- 用户希望自己在云桌面侧看到 Codex 打开的窗口。

## 角色

```text
Codex 本地机器
  -> SSH 到公网跳板机的反向端口

公网跳板机，例如阿里云 ECS
  -> 提供公网 IP，并接收 Gradmotion 发起的反向 SSH 隧道

Gradmotion GUI 云桌面
  -> 主动连出到跳板机，并把自己的 localhost:22 映射到跳板机端口
  -> 运行 Isaac Gym viewer、xclock、gedit 等 GUI 程序
```

## 安全规则

不要写入仓库或聊天记录：

```text
密码
私钥
登录 Token
签名 URL
云桌面控制台的一次性登录链接
```

建议使用临时 SSH key。会话结束后，从 Gradmotion 云桌面的 `/root/.ssh/authorized_keys` 删除这次使用的公钥行。

反向隧道所在终端需要保持运行。按 `Ctrl-C` 或关闭该终端后，Codex 侧连接会断开。

长时间训练、收费任务、删除任务、停止任务等操作仍然需要用户明确确认。

## 1. 准备跳板机

跳板机需要有公网 IP，并允许 SSH 登录。

在跳板机上确认 SSH 服务正常：

```bash
ss -lntp | grep ':22'
systemctl status ssh || service ssh status
```

如果反向端口需要让 Codex 本地直接访问，跳板机还需要满足：

```text
安全组放行反向端口，例如 2222。
sshd_config 允许 TCP 转发。
必要时设置 GatewayPorts yes，让反向端口监听 0.0.0.0。
```

修改 `/etc/ssh/sshd_config` 后需要重启 SSH：

```bash
systemctl restart ssh || service ssh restart
```

## 2. 准备临时 SSH key

在 Codex 本地机器生成临时 key，示例：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\codex_gradmotion_ed25519" -C "codex-gradmotion-temp"
```

只把 `.pub` 公钥内容复制到 Gradmotion 云桌面。不要发送或提交私钥文件。

在 Gradmotion 云桌面里追加公钥：

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
cat >> /root/.ssh/authorized_keys <<'EOF'
<粘贴 codex_gradmotion_ed25519.pub 的单行公钥>
EOF
chmod 600 /root/.ssh/authorized_keys
```

## 3. 从 Gradmotion 发起反向隧道

在 Gradmotion 云桌面终端执行：

```bash
ssh -N -R 2222:localhost:22 root@<ECS_PUBLIC_IP>
```

第一次连接会提示确认 host key，确认 IP 和指纹后输入：

```text
yes
```

如果要求输入跳板机密码，输入 ECS 的 root 密码或使用 ECS 已配置的登录 key。

输入密码后终端看起来“卡住”是正常现象。`-N` 表示不执行远程命令，只保持隧道。

在跳板机上确认端口已经监听：

```bash
ss -lntp | grep 2222
```

期望看到类似：

```text
LISTEN 0 128 0.0.0.0:2222 0.0.0.0:* users:(("sshd",...))
```

## 4. Codex 本地连接 Gradmotion

Codex 本地通过跳板机公网 IP 和反向端口连接 Gradmotion：

```powershell
ssh -i "$env:USERPROFILE\.ssh\codex_gradmotion_ed25519" `
  -p 2222 `
  root@<ECS_PUBLIC_IP> `
  "hostname && pwd && echo tunnel-login-ok"
```

如果输出的是 Gradmotion 云桌面的 hostname，并看到 `tunnel-login-ok`，说明链路可用。

常见问题：

```text
Connection timed out
  通常是安全组没有放行端口，或反向隧道没有保持运行。

Connection closed
  通常是反向隧道断开，或跳板机 sshd 不允许该转发方式。

Permission denied
  通常是 Gradmotion /root/.ssh/authorized_keys 没有加入对应公钥，或私钥不匹配。
```

## 5. 让 GUI 程序显示在云桌面

从 SSH 登录进去的 root shell 通常没有正确的 `DISPLAY` 和 `XAUTHORITY`。这时直接运行 `xclock` 或 Isaac Gym viewer，可能进程存在但用户看不到窗口。

先在 Gradmotion 上识别真正的图形会话：

```bash
who
ls -la /tmp/.X11-unix
ps -ef | egrep 'Xorg|gnome-shell|Xwayland'
```

常见结果：

```text
X socket: /tmp/.X11-unix/X1
DISPLAY: :1
GUI user: gm_xxxxx
XAUTHORITY: /home/gm_xxxxx/.Xauthority
```

用 GUI 用户打开一个小窗口测试：

```bash
runuser -u <GUI_USER> -- \
  env DISPLAY=:1 XAUTHORITY=/home/<GUI_USER>/.Xauthority \
  setsid -f xclock
```

如果云桌面里出现 `xclock`，说明 Codex 通过 SSH 启动的 GUI 程序可以被用户看到。

## 6. 使用项目脚本检测 GUI 环境

本仓库提供了 Gradmotion GUI 云桌面辅助脚本：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-env
```

该命令会尽量自动探测：

```text
GUI_USER
DISPLAY
XAUTHORITY
/tmp/.X11-unix
```

打开一个测试 GUI 程序：

```bash
bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

如果需要手动指定：

```bash
GUI_USER=<GUI_USER> DISPLAY=:1 XAUTHORITY=/home/<GUI_USER>/.Xauthority \
  bash ops/gradmotion/gui-desktop-train.sh open-app xclock
```

## 7. 启动 Isaac Gym viewer

在 Gradmotion 项目目录中：

```bash
cd /root/limx_rl/f1_train
git pull
python -m pip install -e .
```

先跑单环境 viewer smoke test：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-single
```

再跑 16 环境 viewer smoke test：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-smoke
```

如果需要让 Isaac Gym viewer 长时间留在云桌面里，不要直接挂在当前 SSH 会话下，使用后台保持模式：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-hold
```

该命令会用 `nohup` 在后台启动 1 环境 viewer，并把日志写到：

```text
/tmp/codex_isaac_viewer_hold.log
```

查看状态：

```bash
bash ops/gradmotion/gui-desktop-train.sh gui-hold-status
```

关闭后台 viewer：

```bash
bash ops/gradmotion/gui-desktop-train.sh stop-gui-hold
```

如果自动探测失败，手动带上 GUI 环境：

```bash
GUI_USER=<GUI_USER> DISPLAY=:1 XAUTHORITY=/home/<GUI_USER>/.Xauthority \
  bash ops/gradmotion/gui-desktop-train.sh gui-single
```

新机器完整引导优先使用：

```bash
bash ops/gradmotion/bootstrap-gui-desktop.sh
```

默认只做安装、环境检查和 viewer smoke test。正式长训练需要显式指定：

```bash
RUN_NAME=f1_29dof_v1 bash ops/gradmotion/bootstrap-gui-desktop.sh --train
```

## 8. 会话结束清理

在 Gradmotion 云桌面中停止反向隧道：

```text
回到运行 ssh -N -R 的终端，按 Ctrl-C。
```

删除本次临时公钥：

```bash
sed -i '/codex-gradmotion/d' /root/.ssh/authorized_keys
```

如不再需要，也可以在跳板机安全组关闭反向端口，例如 `2222`。

Codex 本地临时私钥保存在本机，不应提交到仓库。需要废弃时，在本地删除对应私钥和公钥文件。
