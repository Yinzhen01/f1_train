# F1 29DOF 远端训练部署流程

本文档用于将本地最新的 `agibot_x1_train` 项目部署到远端服务器，并启动 `f1_dh_stand` 训练任务。

适用前提：

- 远端系统：Ubuntu 20.04
- 远端已安装 Isaac Gym Preview 4
- 远端有 NVIDIA GPU
- 本地使用 WSL/Linux 打包项目
- F1 训练任务名：`f1_dh_stand`

## 1. 本地打包

不要使用 Windows 右键压缩 zip。之前出现过 `.py` 文件被写入空字节的问题。推荐在 WSL 中使用 `tar.gz`。

```bash
cd /mnt/e/Projects

tar \
  --exclude='agibot_x1_train/.git' \
  --exclude='agibot_x1_train/logs' \
  --exclude='agibot_x1_train/**/__pycache__' \
  -czf agibot_x1_train.tar.gz agibot_x1_train
```

本地解压检查：

```bash
rm -rf /tmp/agibot_check
mkdir -p /tmp/agibot_check
tar -xzf agibot_x1_train.tar.gz -C /tmp/agibot_check

python3 - <<'PY'
from pathlib import Path
root = Path("/tmp/agibot_check/agibot_x1_train")
bad = [str(p) for p in root.rglob("*.py") if b"\0" in p.read_bytes()]
print("\n".join(bad) if bad else "local tar ok: no null bytes")
PY
```

期望输出：

```text
local tar ok: no null bytes
```

## 2. 上传到远端

```bash
scp /mnt/e/Projects/agibot_x1_train.tar.gz root@服务器IP:/home/gm_dexoyil185/Documents/
```

远端解压：

```bash
cd /home/gm_dexoyil185/Documents
mv agibot_x1_train agibot_x1_train_bak_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
tar -xzf agibot_x1_train.tar.gz
cd agibot_x1_train
```

检查源码是否正常：

```bash
python - <<'PY'
from pathlib import Path
bad = [str(p) for p in Path(".").rglob("*.py") if b"\0" in p.read_bytes()]
print("\n".join(bad) if bad else "server copy ok: no null bytes")
PY
```

期望输出：

```text
server copy ok: no null bytes
```

## 3. 检查远端环境

确认 GPU：

```bash
nvidia-smi
```

确认 Isaac Gym、Python、PyTorch：

```bash
python --version

python - <<'PY'
from isaacgym import gymapi
import torch
print("isaacgym ok")
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("torch cuda:", torch.version.cuda)
PY
```

注意：Isaac Gym 要求先导入 `isaacgym`，再导入 `torch`。

## 4. 安装项目

```bash
cd /home/gm_dexoyil185/Documents/agibot_x1_train
pip install -e .
```

如果使用 wandb：

```bash
python - <<'PY'
import wandb
print("wandb ok", wandb.__version__)
PY
```

如果不希望在线记录，训练命令前加：

```bash
WANDB_MODE=offline
```

## 5. 检查 F1 任务

```bash
python - <<'PY'
import humanoid.envs
from humanoid.utils import task_registry

env_cfg, _ = task_registry.get_cfgs(name="f1_dh_stand")
print("asset:", env_cfg.asset.file)
print("num_actions:", env_cfg.env.num_actions)
print("num_single_obs:", env_cfg.env.num_single_obs)
print("single_num_privileged_obs:", env_cfg.env.single_num_privileged_obs)
print("default joints:", len(env_cfg.init_state.default_joint_angles))
print("action scales:", len(env_cfg.control.action_scale))
PY
```

期望关键输出：

```text
num_actions: 29
num_single_obs: 98
single_num_privileged_obs: 141
default joints: 29
action scales: 29
```

## 6. Smoke Test

先跑小规模训练，确认 URDF、mesh、维度、Isaac Gym tensor 都正常。

```bash
WANDB_MODE=offline python humanoid/scripts/train.py \
  --task=f1_dh_stand \
  --headless \
  --num_envs=64 \
  --max_iterations=10
```

重点检查是否出现：

- URDF 加载失败
- mesh 路径错误
- shape mismatch
- missing joint key
- gymtorch / CUDA 报错

## 7. 正式训练

```bash
WANDB_MODE=offline python humanoid/scripts/train.py \
  --task=f1_dh_stand \
  --headless \
  --run_name=f1_29dof_v1
```

指定 GPU：

```bash
CUDA_VISIBLE_DEVICES=0 WANDB_MODE=offline python humanoid/scripts/train.py \
  --task=f1_dh_stand \
  --headless \
  --run_name=f1_29dof_v1
```

## 8. 带界面训练测试

如果远端有云桌面/图形界面，可以不加 `--headless`，让 Isaac Gym 打开 viewer 做可视化 smoke test。

先确认图形环境：

```bash
echo $DISPLAY
nvidia-smi
```

如果 `DISPLAY` 为空，可尝试：

```bash
export DISPLAY=:0
```

带界面小规模测试：

```bash
WANDB_MODE=offline python humanoid/scripts/train.py \
  --task=f1_dh_stand \
  --num_envs=16 \
  --max_iterations=10
```

更轻量的单环境测试：

```bash
WANDB_MODE=offline python humanoid/scripts/train.py \
  --task=f1_dh_stand \
  --num_envs=1 \
  --max_iterations=10
```

注意：

- 带 viewer 时不要使用 `--headless`。
- 图形测试只用于确认模型加载、接触、姿态和训练流程是否正常。
- 正式训练仍建议使用 `--headless`，速度更快也更稳定。
- 如果 viewer 黑屏、闪退或卡死，先回到 headless smoke test 排查训练逻辑。

如果已经训练出模型，可以用 `play.py` 打开界面回放策略：

```bash
python humanoid/scripts/play.py \
  --task=f1_dh_stand \
  --load_run=<run_name>
```

如果只想看 TensorBoard 训练曲线，则不需要 Isaac Gym viewer：

```bash
tensorboard --logdir logs/f1_dh_stand --host 0.0.0.0 --port 6006
```

浏览器打开：

```text
http://localhost:6006
```

## 9. 监控训练

查看 GPU：

```bash
watch -n 1 nvidia-smi
```

查看日志：

```bash
ls logs/f1_dh_stand/exported_data
```

启动 TensorBoard：

```bash
tensorboard --logdir logs/f1_dh_stand --host 0.0.0.0 --port 6006
```

本地端口转发：

```bash
ssh -L 6006:localhost:6006 root@服务器IP
```

浏览器打开：

```text
http://localhost:6006
```

## 10. 导出策略

导出 JIT：

```bash
python humanoid/scripts/export_policy_dh.py \
  --task=f1_dh_stand \
  --load_run=<run_name>
```

导出 ONNX：

```bash
python humanoid/scripts/export_onnx_dh.py \
  --task=f1_dh_stand \
  --load_run=<run_name>
```

## 11. 常见问题

### PyTorch 先于 Isaac Gym 导入

错误：

```text
ImportError: PyTorch was imported before isaacgym modules.
```

处理：

- 确认代码中 `from isaacgym import gymapi/gymutil` 在 `import torch` 之前。
- 当前项目需要保留 `humanoid/utils/helpers.py` 中的导入顺序修复。

### task_registry 循环导入

错误类似：

```text
ImportError: cannot import name 'task_registry' from partially initialized module
```

处理：

- 当前项目需要保留 `humanoid/utils/task_registry.py` 中的 `TYPE_CHECKING` 类型导入修复。
- 检查 `humanoid/utils/__init__.py` 不要重新导出 `Terrain`。

### 源码文件含有空字节

错误：

```text
ValueError: source code string cannot contain null bytes
```

处理：

- 不要使用 Windows zip。
- 重新用 WSL/Linux `tar.gz` 打包上传。
- 上传后执行 null bytes 检查。

### gymtorch / CUDA 兼容问题

如果出现 `gymtorch`、CUDA extension、illegal memory access 等问题，优先考虑 PyTorch 与 Isaac Gym 兼容性。

推荐环境：

```text
Python 3.8
PyTorch 1.13.1
CUDA 11.7
numpy 1.23
Isaac Gym Preview 4
```

如果远端已有 PyTorch 2.x 且 smoke test 能通过，可以先继续使用。

## 12. 当前 F1 注意事项

- F1 当前训练使用 URDF：

```text
resources/robots/Models/urdf/F1_29DOF_physically_mirrored.urdf
```

- 当前任务是 29DOF 全关节 action：

```text
f1_dh_stand
```

- 当前尚未接入 SMPL motion imitation，只完成 F1 29DOF 环境与训练配置适配。
- 当前没有 F1 MJCF，因此 `sim2sim.py` 不能直接用于 F1 MuJoCo 验证。
