# 通过 gm-cli 提交云训练任务流程与问题记录

本文整理本项目通过 `gm-cli` 提交 Gradmotion 云训练任务的完整流程、成功配置、排查过程和最终结论。

## 1. 背景

当前项目本地路径：

```text
E:\Projects\agibot_x1_train
```

代码已推送到 GitHub 仓库：

```text
https://github.com/Yinzhen01/f1_train.git
branch: main
commit: 64e0501f72dc8759481c487e50a3ea2c5d564aa2
```

最终验证任务使用：

```text
任务 ID: TASK_20260608_073
资源: A10 / ESKU000004
镜像: Isaac GYM:preview-4 / BJX00000001 / V000124
状态: Completed
```

## 2. Windows 下 gm-cli 调用方式

PowerShell 中 `gm` 默认可能被解析为 `Get-Member` 别名，因此不要直接执行：

```powershell
gm --help
```

应使用 npm shim 的完整路径：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --help
```

后续所有命令均推荐使用：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" <subcommand>
```

## 3. 标准提交任务流程

### 3.1 查询项目

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" project list --page 1 --limit 20
```

本次使用：

```text
projectId: PRO_20260605_003
projectName: 【官方示例工程】Tron1双点足机器人行走训练
```

### 3.2 查询资源规格

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task resource list --goods-back-category 3 --page 1 --limit 50
```

本次测试过：

```text
ESKU000011: 1*4090D*24G（不可挂载数据）  启动时报资源繁忙
ESKU000004: 1*A10*24G                  成功运行 smoke test
```

最终使用：

```text
goodsId: ESKU000004
goodsName: 1*A10*24G
```

### 3.3 查询镜像

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task image official
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task image versions --image-id "BJX00000001"
```

本次使用：

```text
imageId: BJX00000001
imageName: Isaac GYM:preview-4
imageVersion: V000124
versionCode: isaac-gym-v19
```

### 3.4 生成 create JSON

`gm-cli` 创建任务推荐使用 JSON 文件：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task create --file ./create-task.json
```

不要把 `create-*.json` 这类临时 payload 提交到 Git。当前 `.gitignore` 已加入：

```gitignore
create-*.json
edit-*.json
copy-*.json
```

## 4. 成功任务 JSON 模板

下面是本项目已验证成功的 smoke test 配置。正式训练时可基于此模板修改任务名、训练步数和资源规格。

```json
{
  "taskBaseInfo": {
    "projectId": "PRO_20260605_003",
    "taskType": "1",
    "trainType": "1",
    "taskName": "f1-29dof-smoke-a10-public-20260608",
    "taskDescription": "Smoke validation task for F1 29DOF on A10.",
    "taskTag": [
      "f1",
      "29dof",
      "smoke",
      "a10",
      "isaac-gym"
    ],
    "goodsId": "ESKU000004",
    "imageId": "BJX00000001",
    "imageVersion": "V000124",
    "personalDataPath": "/personal"
  },
  "taskCodeInfo": {
    "codeType": "2",
    "codeUrl": "[{\"codeUrl\":\"https://github.com/Yinzhen01/f1_train.git\",\"versionType\":\"1\",\"versionName\":\"main\"}]",
    "versionType": "1",
    "versionName": "main",
    "mainCodeUri": "f1_train/humanoid/scripts/train.py",
    "hparamsPath": "f1_train/humanoid/envs/f1/f1_dh_stand_config.py",
    "startScript": "gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_stand --headless --num_envs=16 --max_iterations=5",
    "isOpen": "1"
  },
  "runtimeReminderConfig": {
    "enableRuntimeReminder": false,
    "reminderDurations": []
  }
}
```

关键约束：

- `codeType` 使用 `"2"`，表示 Git 仓库。
- `codeUrl` 是字符串化的 JSON 数组。
- `versionType` / `versionName` 建议显式填写。
- `mainCodeUri` / `hparamsPath` / `startScript` 路径需要从仓库目录名 `f1_train/` 开始。
- `startScript` 必须以 `gm-run` 开头，不能写 `python train.py`。

## 5. dry-run、创建、启动和查看日志

### 5.1 dry-run

所有写操作建议先 dry-run：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task create --file ./create-task.json --dry-run
```

`dry-run` 成功时可能返回非 0 退出码，但输出中会有：

```json
"success": true,
"dry_run": true
```

### 5.2 正式创建任务

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --yes task create --file ./create-task.json
```

成功后返回：

```json
{
  "taskId": "TASK_xxx"
}
```

### 5.3 启动任务

先 dry-run：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --yes task run --task-id "TASK_xxx" --dry-run
```

正式启动：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --yes task run --task-id "TASK_xxx"
```

### 5.4 查看状态和日志

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task info --task-id "TASK_xxx"
```

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task logs --task-id "TASK_xxx" --follow --interval 5s --timeout 2m --raw --no-request-log
```

常见状态：

```text
0: created / 未运行
2: pending / 等待调度
3: running / 运行中
5: finished / completed
6: failed
```

## 6. 本次问题与解决方式

### 6.1 PowerShell 中 gm 被解析为 Get-Member

现象：

```text
gm : 必须为 Get-Member cmdlet 指定一个对象
```

原因：

```text
PowerShell 内置 gm 别名指向 Get-Member。
```

解决：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" ...
```

该规则已写入本地 `gm-cli` skill。

### 6.2 4090D 低价规格启动失败

任务：

```text
TASK_20260608_053
goodsId: ESKU000011
```

错误：

```text
系统算力资源繁忙，请稍后再试！
```

处理：

```text
改用 A10 规格 ESKU000004 后，任务可进入 pending/running 并完成 smoke test。
```

### 6.3 private 仓库未成功拉取代码

现象：

```text
python: can't open file 'f1_train/humanoid/scripts/train.py': [Errno 2] No such file or directory
```

任务详情中：

```text
commitId: ""
```

排查过程：

1. GitHub 账号名一开始填的是邮箱，应填写 GitHub username：

```text
Yinzhen01
```

2. GitHub token 一开始缺少代码读取权限，应至少具有：

```text
Repository access: Yinzhen01/f1_train
Repository permissions: code / contents read
```

3. 补充 token 权限后，private 任务仍未成功记录 `commitId`。

4. 将仓库改为 public 后，任务成功拉取代码，`commitId` 正常出现。

结论：

```text
训练配置和路径没有问题；private 仓库失败主要与 Gradmotion 平台 Git 凭证配置或权限生效有关。
```

### 6.4 路径格式试错

测试过以下 `startScript` 路径：

```text
gm-run f1_train/humanoid/scripts/train.py ...
gm-run humanoid/scripts/train.py ...
gm-run train.py ...
```

最终成功路径：

```text
gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_stand --headless --num_envs=16 --max_iterations=5
```

说明：

```text
平台拉取 public 仓库后，代码位于 /workspace/f1_train/。
因此 mainCodeUri、hparamsPath 和 startScript 均应带 f1_train/ 前缀。
```

## 7. 最终成功验证结果

成功任务：

```text
taskId: TASK_20260608_073
taskName: f1-29dof-smoke-a10-public-20260608
taskStatus: 5
commitId: 64e0501f72dc8759481c487e50a3ea2c5d564aa2
runtime: 334 秒
```

日志关键内容：

```text
/workspace/f1_train/...
Learning iteration 0/5
Learning iteration 1/5
Learning iteration 2/5
Learning iteration 3/5
Learning iteration 4/5
Task(TASK_20260608_073) status updated to: Completed
model_0.pt uploaded successfully
model_5.pt uploaded successfully
```

这说明：

```text
Git 仓库拉取成功。
Isaac Gym 环境可用。
F1 29DOF 任务可注册。
训练入口、URDF、环境配置和 PPO 流程可以跑通。
模型 checkpoint 可被平台识别并上传。
```

## 8. 正式训练建议

基于成功 smoke test，可以将启动命令改为正式训练规模，例如：

```text
gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_stand --headless --num_envs=4096 --max_iterations=3000
```

建议仍然先用较小规模验证：

```text
--num_envs=64 --max_iterations=20
```

确认稳定后再扩大。

## 9. private 仓库后续排查标准

如果将仓库改回 private，需要重新创建任务验证，不要复用旧任务。

判断是否成功拉取 private 仓库的标准：

```text
gm task info 中 taskCodeInfo.commitId 不为空。
日志中出现 /workspace/f1_train/ 相关文件。
不再出现 can't open file。
```

如果 `commitId` 仍为空，优先检查：

```text
Gradmotion 个人设置 -> Git 信息
GitHub 账号名: Yinzhen01
GitHub Token: 具备 Yinzhen01/f1_train 的 code/contents read 权限
```

如果 private 仍失败，而 public 可以成功，则说明问题仍在平台侧 private Git 凭证链路。

## 10. 新对话接手时的状态审计

新对话如果需要继续提交任务、建立环境或启动完整训练，应先读取本文档，并执行一次状态审计，不要直接创建新任务。

建议在新对话中这样提问：

```text
请读取 E:\Projects\agibot_x1_train\doc\gm_cli_task_submission_workflow.md，
先审计当前项目和云平台状态，列出已完成事项、缺失/待确认事项、下一步建议。
不要直接创建任务，等我确认。
```

推荐审计命令：

```powershell
git remote -v
git branch --show-current
git log --oneline --decorate -5
git status --short --branch
Get-ChildItem -Path . -Filter "create-*.json"
```

检查 gm-cli：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --help
```

检查云平台成功任务：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task info --task-id "TASK_20260608_073"
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" task logs --task-id "TASK_20260608_073"
```

判断规则：

```text
如果 create-*.json 存在：可先读取并复用，必要时按本文档模板修正。
如果 create-*.json 不存在：按第 4 节模板重新生成。
如果 taskCodeInfo.commitId 不为空：说明平台已成功拉到 Git 仓库。
如果 taskStatus 为 5：说明任务已完成。
如果 taskStatus 为 6：读取 logs 定位失败原因。
如果仓库为 private 且 commitId 为空：优先排查 Gradmotion Git 信息和 GitHub token 权限。
```

## 11. 当前项目状态快照

截至本文档整理时，已完成：

```text
本地 main 已推送到 GitHub: https://github.com/Yinzhen01/f1_train.git
成功 smoke 任务: TASK_20260608_073
成功资源规格: ESKU000004 / 1*A10*24G
成功镜像版本: BJX00000001 / V000124
成功 Git commit: 64e0501f72dc8759481c487e50a3ea2c5d564aa2
成功启动命令: gm-run f1_train/humanoid/scripts/train.py --task=f1_dh_stand --headless --num_envs=16 --max_iterations=5
```

当前本地存在多个历史测试 payload：

```text
create-train.json
create-validate.json
create-validate-a10.json
create-validate-a10-rootpath.json
create-validate-a10-workdir.json
create-validate-a10-versionfields.json
create-validate-a10-tokenfix.json
create-validate-a10-public.json
```

这些文件是临时请求体，已由 `.gitignore` 中的规则排除：

```gitignore
create-*.json
edit-*.json
copy-*.json
```

后续正式训练建议优先基于已验证成功的 `create-validate-a10-public.json` 结构生成新 payload，而不是复用路径试错失败的历史 payload。

仍待确认：

```text
如果仓库改回 private，需要重新验证 Gradmotion 是否能拉取 private GitHub 仓库。
private 验证通过的标准是 taskCodeInfo.commitId 不为空，并且日志出现 /workspace/f1_train/。
正式长训练尚未启动，只完成了 5 iteration smoke test。
```
