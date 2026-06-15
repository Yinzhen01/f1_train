# Gradmotion 多账号申请与配置流程

本文档用于管理多个 Gradmotion 账号的申请、初始化、gm-cli profile 配置、账号巡检和训练任务提交前检查。

配合以下文档使用：

```text
doc/gm_cli_task_submission_workflow.md
doc/project_structure_and_cleanup.md
doc/cloud_task_artifact_layout.md
```

## 1. 目标

当单个 Gradmotion 账号无法充值、余额不足或资源受限时，可以把训练任务分散到多个合规账号中管理。

核心目标：

```text
每个 Gradmotion 账号对应一个 gm-cli profile。
不把 API key、密码、GitHub token、充值记录写入 Git。
能追踪每个任务由哪个账号提交。
提交训练前检查账号、项目、资源、镜像和运行中任务。
用初始额度、资源单价和任务时长估算剩余额度。
创建或启动长时间、可能计费的训练任务前必须等待用户确认。
```

## 2. 新账号申请记录

每申请一个新 Gradmotion 账号，先在 Git 仓库外记录以下信息：

```text
Gradmotion 登录账号、邮箱或手机号
API key
账号归属人或用途
是否可充值、是否有可用额度
初始额度
常用资源单价
Gradmotion 内绑定的 GitHub 账号名
如果使用 private 仓库，GitHub token 权限是否正确
账号可见的 projectId
```

禁止写入仓库：

```text
Gradmotion 密码
API key
GitHub token
充值截图或付款信息
签名下载 URL
```

## 3. GitHub 仓库权限

本项目 public GitHub 仓库模式已经验证可用。若继续使用 public 仓库，新账号只需要确认项目、资源和任务权限。

如果仓库改为 private，每个 Gradmotion 账号都需要在平台个人设置里配置 Git 信息：

```text
GitHub account name: Yinzhen01
GitHub token: 必须有读取 Yinzhen01/f1_train 代码内容的权限
```

private 仓库配置只有在以下两项同时满足时才算成功：

```text
taskCodeInfo.commitId 非空
任务日志里能看到 /workspace/f1_train/，且没有 can't open file
```

## 4. gm-cli Profile 配置

Windows 上不要直接运行 `gm`，因为 PowerShell 可能把它解析成 `Get-Member`。

统一使用：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" <args>
```

每个账号创建一个独立 profile：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" config profile set gm_f1_01 --api-key "<API_KEY>"
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" config profile set gm_f1_02 --api-key "<API_KEY>"
```

推荐命名：

```text
gm_f1_01
gm_f1_02
gm_f1_03
```

日常命令优先显式带 `--profile`，避免误用当前默认账号：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 auth whoami
```

仅手动调试时才切换默认 profile：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" config profile use gm_f1_01
```

查看本机已有 profile：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" config profile list
```

## 5. 本地账号台账

本地维护一个不提交 Git 的账号台账：

```text
ops/gm-cli/accounts.local.json
```

此文件只记录 profile 名和运行状态，不保存 API key。

建议结构：

```json
{
  "accounts": [
    {
      "profile": "gm_f1_01",
      "status": "active",
      "owner": "local",
      "purpose": "f1_train",
      "projectId": "PRO_xxx",
      "preferredGoodsId": "ESKU000004",
      "preferredImageId": "BJX00000001",
      "preferredImageVersion": "V000124",
      "credit": {
        "initial": 0,
        "unit": "CNY",
        "estimatedUsed": 0,
        "estimatedReserved": 0,
        "estimatedRemaining": 0,
        "safetyReserve": 0
      },
      "priceBook": [
        {
          "goodsId": "ESKU000004",
          "goodsName": "1*A10*24G",
          "unitPricePerHour": 0,
          "billingGranularityMinutes": 60
        }
      ],
      "usage": [
        {
          "taskId": "TASK_xxx",
          "goodsId": "ESKU000004",
          "status": "finished",
          "durationMinutes": 0,
          "estimatedCost": 0
        }
      ],
      "lastCheckedAt": "2026-06-15",
      "notes": "A10 known-good path; no API key stored here."
    }
  ]
}
```

推荐状态值：

```text
active       可用于新任务
low_balance 余额或充值异常，不启动新训练
cooling      临时暂停，等待资源或人工决定
blocked      认证、项目、Git 或任务权限异常
retired      不再使用
```

## 6. 额度估算规则

gm-cli 不能直接获取账号剩余额度时，本地台账使用估算余额。

可获取或人工录入的数据：

```text
initialCredit：账号初始额度
unitPricePerHour：资源单价
durationMinutes：任务运行时长
billingGranularityMinutes：计费粒度，未知时按 60 分钟保守估算
safetyReserve：安全预留额度，避免余额贴边提交
```

估算公式：

```text
billableHours = ceil(durationMinutes / billingGranularityMinutes) * billingGranularityMinutes / 60
taskEstimatedCost = billableHours * unitPricePerHour
estimatedUsed = sum(finished/stopped/failed tasks estimated cost)
estimatedReserved = sum(created/pending/running/deploying tasks reserved cost)
estimatedRemaining = initialCredit - estimatedUsed - estimatedReserved
availableForNewTask = estimatedRemaining - safetyReserve
```

使用规则：

```text
任务创建前，用计划训练时长估算 reserved cost。
任务运行中，按当前已运行时长和计划最大时长取较大值估算 reserved cost。
任务完成后，用 gm task info 或日志中的实际运行时长回填 usage。
如果平台或账单页面显示真实消费，以真实消费修正 estimatedUsed。
如果 estimatedRemaining 不可信，把账号状态改为 cooling 或 low_balance，等待人工确认。
```

提交新任务前，预计任务费用必须小于 `availableForNewTask`。如果不足，不能选择该账号。

## 7. 新账号验证流程

配置 profile 后，依次验证：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 auth status
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 auth whoami
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 project list --page 1 --limit 20
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task resource list --goods-back-category 3 --page 1 --limit 50
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task image official
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task image versions --image-id "BJX00000001"
```

满足以下条件后，才把台账状态标记为 `active`：

```text
auth status / whoami 成功。
能看到预期项目。
训练资源列表里有可用资源。
初始额度和常用资源单价已经写入本地台账。
已验证镜像 BJX00000001 / V000124 可用，或记录替代镜像。
如果使用 private 仓库，GitHub 读取权限已经验证。
```

## 8. 提交任务前账号选择

对候选账号逐个检查：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task list --status "2,3,4" --page 1 --limit 50
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 project list --page 1 --limit 20
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task resource list --goods-back-category 3 --page 1 --limit 50
```

账号选择优先级：

```text
台账状态为 active。
估算剩余额度充足，且扣除 safetyReserve 后能覆盖本次预计费用。
pending / running / deploying 任务最少。
projectId 有效。
资源和镜像可用。
近期没有认证、Git、余额、资源失败记录。
```

然后用选中的 profile 做 dry-run：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task create --file .\ops\gm-cli\payloads\create-train.json --dry-run
```

dry-run 通过并汇报后，等待用户确认，再创建或启动正式任务：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 --yes task create --file .\ops\gm-cli\payloads\create-train.json
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 --yes task run --task-id "TASK_xxx"
```

创建成功后，立即把 `TASK_xxx` 写入 `usage`，状态先记为 `created` 或 `pending`，并把预计费用计入 `estimatedReserved`。

## 9. 任务命名和标签

任务名和 tag 里写入账号 profile 简写，方便后续追踪：

```text
taskName: f1-dh-stand-a10-gm01-20260613
taskTag: f1, 29dof, train, a10, gm01
```

云端产物下载后仍按现有规则保存：

```text
cloud_artifacts/tasks/<TASK_ID>/
```

新完成任务优先用下载 helper，它会下载并同步到推理仓库：

```powershell
powershell -ExecutionPolicy Bypass -File .\ops\gm-cli\download-task-artifacts.ps1 -TaskId TASK_xxx
```

## 10. 任务完成后的台账回填

任务完成、失败或停止后，先查询任务状态和运行时长：

```powershell
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task info --task-id "TASK_xxx"
& "C:\Users\HP\AppData\Roaming\npm\gm.cmd" --profile gm_f1_01 task logs --task-id "TASK_xxx" --raw --no-request-log
```

回填台账：

```text
usage[].status
usage[].durationMinutes
usage[].estimatedCost
credit.estimatedUsed
credit.estimatedReserved
credit.estimatedRemaining
lastCheckedAt
```

如果任务失败但已经运行过，也要按实际运行时长估算消费。不要因为任务失败就把费用记为 0，除非平台账单明确显示未计费。

## 11. 异常处理

账号验证或提交失败时，按下面规则更新台账：

```text
401/403 认证失败：标记 blocked，刷新 API key 或重建 profile。
项目不可见：标记 blocked，先检查 Gradmotion 项目权限。
资源不可用：如果无替代资源，标记 cooling。
估算余额不足、充值异常或账单不确定：标记 low_balance 或 cooling。
private Git 拉取失败：检查 GitHub 账号名、token 权限和 taskCodeInfo.commitId。
```

不要把失败 payload 放到仓库根目录。临时 payload 保持在：

```text
ops/gm-cli/payloads/
```

不要把原始日志、checkpoint 或签名 URL 放进 `doc/`。云任务产物保持在：

```text
cloud_artifacts/
```
