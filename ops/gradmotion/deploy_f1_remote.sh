#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME_DEFAULT="agibot_x1_train"
PROJECT_NAME="$PROJECT_NAME_DEFAULT"
REMOTE_DIR="/home/gm_dexoyil185/Documents"
TASK="f1_dh_stand"
PYTHON_BIN="python"
LOCAL_PYTHON_BIN="python3"
CONDA_ENV=""
REMOTE=""
GPU=""
WANDB_MODE_VALUE="offline"
SMOKE_ENVS="64"
SMOKE_ITERS="10"
RUN_PACKAGE="1"
RUN_UPLOAD="1"
RUN_SMOKE="1"
RUN_ENV_FIX="1"
PACKAGE_ONLY="0"
LOCAL_DEPLOY="0"
ARCHIVE_PATH=""

usage() {
  cat <<'EOF'
Usage:
  bash ops/gradmotion/deploy_f1_remote.sh --server root@SERVER_IP [options]
  bash ops/gradmotion/deploy_f1_remote.sh --local-deploy --archive ./agibot_x1_train.tar.gz [options]

Common examples:
  # Step 1: run on the old/local computer, then manually copy the tar.gz and this script.
  bash ops/gradmotion/deploy_f1_remote.sh --package-only

  # Step 2: run on the new/remote computer after manual copy.
  bash ops/gradmotion/deploy_f1_remote.sh --local-deploy --archive ./agibot_x1_train.tar.gz --conda-env pointfoot_legged_gym --gpu 0
  bash ops/gradmotion/deploy_f1_remote.sh --local-deploy --archive ./agibot_x1_train.tar.gz --gpu 0

  # Optional: one-command SSH upload/deploy mode.
  bash ops/gradmotion/deploy_f1_remote.sh --server root@1.2.3.4
  bash ops/gradmotion/deploy_f1_remote.sh --server user@1.2.3.4 --conda-env pointfoot_legged_gym --gpu 0
  bash ops/gradmotion/deploy_f1_remote.sh --server root@1.2.3.4 --skip-smoke

Options:
  --server HOST          Remote SSH target, for example root@1.2.3.4.
  --local-deploy         Deploy on the current machine from an existing tar.gz archive.
  --remote-dir DIR      Target parent directory. Default: /home/gm_dexoyil185/Documents.
  --project-name NAME    Project directory inside the archive. Default: agibot_x1_train.
  --task TASK           Training task to validate. Default: f1_dh_stand.
  --python CMD          Remote Python executable. Default: python.
  --local-python CMD    Local Python executable for tar integrity check. Default: python3.
  --conda-env NAME      Activate this conda env before install/checks. Omit it to use the current shell env.
  --gpu ID              Export CUDA_VISIBLE_DEVICES=ID before smoke test.
  --smoke-envs N        Number of envs for smoke test. Default: 64.
  --smoke-iters N       Max iterations for smoke test. Default: 10.
  --archive PATH        Local tar.gz path. Default: ../agibot_x1_train.tar.gz.
  --skip-package        Reuse an existing local archive instead of creating one.
  --skip-upload         Reuse an existing remote archive instead of uploading one.
  --skip-smoke          Install and validate config only, without running train.py.
  --skip-env-fix        Do not auto-install the Isaac Gym recommended Python/PyTorch stack.
  --package-only        Create and verify local tar.gz only.
  -h, --help            Show this help.
EOF
}

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

activate_conda_env() {
  local conda_env="$1"

  if [[ -z "$conda_env" ]]; then
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
      log "Using current conda environment: ${CONDA_DEFAULT_ENV}"
    fi
    return
  fi

  if [[ "${CONDA_DEFAULT_ENV:-}" == "$conda_env" ]]; then
    log "Conda environment already active: ${conda_env}"
    return
  fi

  log "Activating conda environment: ${conda_env}"
  if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
  else
    die "conda.sh not found under ~/miniconda3 or ~/anaconda3"
  fi

  if ! conda env list | awk '{print $1}' | grep -Fxq "$conda_env"; then
    printf 'Available conda environments:\n' >&2
    conda env list >&2
    die "conda environment not found: ${conda_env}"
  fi

  conda activate "$conda_env"
}

install_python_runtime_deps() {
  local python_bin="$1"
  local missing_packages

  missing_packages="$("$python_bin" - <<'PY'
import importlib.util

required = {
    "wandb": "wandb",
}

missing = [
    package
    for module, package in required.items()
    if importlib.util.find_spec(module) is None
]
print(" ".join(missing))
PY
)"

  if [[ -n "$missing_packages" ]]; then
    log "Installing missing Python runtime packages: ${missing_packages}"
    PIP_ROOT_USER_ACTION=ignore "$python_bin" -m pip install $missing_packages
  else
    log "Python runtime packages already available"
  fi
}

ensure_isaacgym_python_stack() {
  local python_bin="$1"

  if [[ "$RUN_ENV_FIX" != "1" ]]; then
    log "Skipping Python/PyTorch compatibility fix"
    return
  fi

  log "Checking Isaac Gym recommended Python stack"
  if "$python_bin" - <<'PY'
import importlib.util
import sys

expected = {
    "python": "3.8",
    "torch": "1.13.1",
    "cuda": "11.7",
    "numpy": "1.23",
}

py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
torch_ver = "missing"
torch_cuda = "missing"
numpy_ver = "missing"

if importlib.util.find_spec("torch") is not None:
    import torch
    torch_ver = torch.__version__
    torch_cuda = str(torch.version.cuda)
if importlib.util.find_spec("numpy") is not None:
    import numpy
    numpy_ver = numpy.__version__

print(f"python: {py_ver}")
print(f"torch: {torch_ver}")
print(f"torch cuda: {torch_cuda}")
print(f"numpy: {numpy_ver}")

ok = (
    py_ver == expected["python"]
    and torch_ver.startswith(expected["torch"])
    and torch_cuda.startswith(expected["cuda"])
    and numpy_ver.startswith(expected["numpy"])
)
raise SystemExit(0 if ok else 1)
PY
  then
    log "Python stack is compatible with Isaac Gym Preview 4"
    return
  fi

  command -v conda >/dev/null || die "conda is required to auto-fix Python/PyTorch/CUDA versions"

  log "Installing Isaac Gym recommended stack: Python 3.8, PyTorch 1.13.1, CUDA 11.7, NumPy 1.23.5"
  conda install -y \
    python=3.8 \
    numpy=1.23.5 \
    pytorch==1.13.1 \
    torchvision==0.14.1 \
    torchaudio==0.13.1 \
    pytorch-cuda=11.7 \
    -c pytorch \
    -c nvidia

  log "Re-checking Python stack"
  "$python_bin" - <<'PY'
import importlib.util
import sys

expected = {
    "python": "3.8",
    "torch": "1.13.1",
    "cuda": "11.7",
    "numpy": "1.23",
}

py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
if importlib.util.find_spec("torch") is None:
    raise SystemExit("torch is still missing after conda install")
if importlib.util.find_spec("numpy") is None:
    raise SystemExit("numpy is still missing after conda install")

import torch
import numpy

print(f"python: {py_ver}")
print(f"torch: {torch.__version__}")
print(f"torch cuda: {torch.version.cuda}")
print(f"numpy: {numpy.__version__}")

if py_ver != expected["python"]:
    raise SystemExit("python version check failed")
if not torch.__version__.startswith(expected["torch"]):
    raise SystemExit("torch version check failed")
if not str(torch.version.cuda).startswith(expected["cuda"]):
    raise SystemExit("torch cuda version check failed")
if not numpy.__version__.startswith(expected["numpy"]):
    raise SystemExit("numpy version check failed")
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server)
      REMOTE="${2:-}"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="${2:-}"
      shift 2
      ;;
    --project-name)
      PROJECT_NAME="${2:-}"
      shift 2
      ;;
    --task)
      TASK="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --local-python)
      LOCAL_PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --conda-env)
      CONDA_ENV="${2:-}"
      shift 2
      ;;
    --gpu)
      GPU="${2:-}"
      shift 2
      ;;
    --smoke-envs)
      SMOKE_ENVS="${2:-}"
      shift 2
      ;;
    --smoke-iters)
      SMOKE_ITERS="${2:-}"
      shift 2
      ;;
    --archive)
      ARCHIVE_PATH="${2:-}"
      shift 2
      ;;
    --skip-package)
      RUN_PACKAGE="0"
      shift
      ;;
    --skip-upload)
      RUN_UPLOAD="0"
      shift
      ;;
    --skip-smoke)
      RUN_SMOKE="0"
      shift
      ;;
    --skip-env-fix)
      RUN_ENV_FIX="0"
      shift
      ;;
    --package-only)
      PACKAGE_ONLY="1"
      shift
      ;;
    --local-deploy)
      LOCAL_DEPLOY="1"
      RUN_PACKAGE="0"
      RUN_UPLOAD="0"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/$PROJECT_NAME_DEFAULT" && "$PROJECT_NAME" == "$PROJECT_NAME_DEFAULT" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR/$PROJECT_NAME"
else
  PROJECT_ROOT="$SCRIPT_DIR"
  if [[ "$(basename "$PROJECT_ROOT")" != "$PROJECT_NAME" ]]; then
    PROJECT_ROOT="$SCRIPT_DIR/$PROJECT_NAME"
  fi
fi
[[ "$PACKAGE_ONLY" != "1" || -d "$PROJECT_ROOT" ]] || die "project directory not found: $PROJECT_ROOT"
PROJECT_PARENT="$(dirname "$SCRIPT_DIR")"
if [[ -z "$ARCHIVE_PATH" ]]; then
  if [[ "$LOCAL_DEPLOY" == "1" ]]; then
    ARCHIVE_PATH="${SCRIPT_DIR}/${PROJECT_NAME}.tar.gz"
  else
    ARCHIVE_PATH="${PROJECT_PARENT}/${PROJECT_NAME}.tar.gz"
  fi
fi
if [[ "$ARCHIVE_PATH" != /* ]]; then
  ARCHIVE_PATH="$(cd "$(dirname "$ARCHIVE_PATH")" && pwd)/$(basename "$ARCHIVE_PATH")"
fi
ARCHIVE_BASENAME="$(basename "$ARCHIVE_PATH")"

package_project() {
  log "Packaging ${PROJECT_NAME} -> ${ARCHIVE_PATH}"
  tar \
    --exclude="${PROJECT_NAME}/.git" \
    --exclude="${PROJECT_NAME}/logs" \
    --exclude="${PROJECT_NAME}/**/__pycache__" \
    --exclude="${PROJECT_NAME}/.pytest_cache" \
    -czf "$ARCHIVE_PATH" \
    -C "$(dirname "$PROJECT_ROOT")" \
    "$(basename "$PROJECT_ROOT")"

  local check_dir
  check_dir="/tmp/${PROJECT_NAME}_deploy_check_$$"
  rm -rf "$check_dir"
  mkdir -p "$check_dir"
  tar -xzf "$ARCHIVE_PATH" -C "$check_dir"

  "$LOCAL_PYTHON_BIN" - "$check_dir/$PROJECT_NAME" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
bad = [str(p) for p in root.rglob("*.py") if b"\0" in p.read_bytes()]
if bad:
    print("\n".join(bad))
    raise SystemExit("local tar check failed: source contains null bytes")
print("local tar ok: no null bytes")
PY

  rm -rf "$check_dir"
}

deploy_on_current_machine() {
  local target_dir="$1"
  local project_name="$2"
  local archive_path="$3"
  local python_bin="$4"
  local conda_env="$5"
  local task="$6"
  local smoke_envs="$7"
  local smoke_iters="$8"
  local run_smoke="$9"
  local gpu="${10}"
  local wandb_mode_value="${11}"

  mkdir -p "$target_dir"
  [[ -f "$archive_path" ]] || die "missing archive: $archive_path"

  activate_conda_env "$conda_env"
  command -v "$python_bin" >/dev/null || die "python executable not found: $python_bin"
  ensure_isaacgym_python_stack "$python_bin"

  cd "$target_dir"
  if [[ -d "$project_name" ]]; then
    local backup_name
    backup_name="${project_name}_bak_$(date +%Y%m%d_%H%M%S)"
    log "Backing up existing ${project_name} -> ${backup_name}"
    mv "$project_name" "$backup_name"
  fi

  log "Extracting ${archive_path}"
  tar -xzf "$archive_path"
  cd "$project_name"

  log "Checking Python source files"
  "$python_bin" - <<'PY'
from pathlib import Path

bad = [str(p) for p in Path(".").rglob("*.py") if b"\0" in p.read_bytes()]
if bad:
    print("\n".join(bad))
    raise SystemExit("server copy check failed: source contains null bytes")
print("server copy ok: no null bytes")
PY

  log "Checking GPU"
  if command -v nvidia-smi >/dev/null; then
    nvidia-smi
  else
    printf 'WARNING: nvidia-smi not found; continuing because some containers hide it.\n'
  fi

  log "Checking Isaac Gym and PyTorch"
  "$python_bin" --version
  "$python_bin" - <<'PY'
from isaacgym import gymapi
import torch

print("isaacgym ok")
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("torch cuda:", torch.version.cuda)
PY

  log "Installing project in editable mode"
  PIP_ROOT_USER_ACTION=ignore "$python_bin" -m pip install -e .

  install_python_runtime_deps "$python_bin"

  log "Checking task configuration"
  "$python_bin" - "$task" <<'PY'
import sys

import humanoid.envs
from humanoid.utils import task_registry

task = sys.argv[1]
env_cfg, _ = task_registry.get_cfgs(name=task)

checks = {
    "num_actions": env_cfg.env.num_actions,
    "num_single_obs": env_cfg.env.num_single_obs,
    "single_num_privileged_obs": env_cfg.env.single_num_privileged_obs,
    "default joints": len(env_cfg.init_state.default_joint_angles),
    "action scales": len(env_cfg.control.action_scale),
}

print("asset:", env_cfg.asset.file)
for key, value in checks.items():
    print(f"{key}: {value}")

expected = {
    "f1_dh_stand": {
        "num_actions": 29,
        "num_single_obs": 98,
        "single_num_privileged_obs": 141,
        "default joints": 29,
        "action scales": 29,
    }
}

if task in expected:
    mismatches = [
        f"{key}: expected {expected[task][key]}, got {value}"
        for key, value in checks.items()
        if expected[task][key] != value
    ]
    if mismatches:
        print("\n".join(mismatches))
        raise SystemExit("task config check failed")
PY

  if [[ "$run_smoke" == "1" ]]; then
    log "Running headless smoke test"
    if [[ -n "$gpu" ]]; then
      export CUDA_VISIBLE_DEVICES="$gpu"
    fi
    export WANDB_MODE="$wandb_mode_value"
    "$python_bin" humanoid/scripts/train.py \
      --task="$task" \
      --headless \
      --num_envs="$smoke_envs" \
      --max_iterations="$smoke_iters"
  else
    log "Skipping smoke test"
  fi

  log "Deployment validation finished"
  printf '\nFormal training command:\n'
  printf '  CUDA_VISIBLE_DEVICES=%s WANDB_MODE=%s %s humanoid/scripts/train.py --task=%s --headless --run_name=f1_29dof_v1\n' \
    "${gpu:-0}" "$wandb_mode_value" "$python_bin" "$task"
}

remote_deploy() {
  log "Preparing remote directory ${REMOTE}:${REMOTE_DIR}"
  ssh "$REMOTE" "mkdir -p \"$REMOTE_DIR\""

  if [[ "$RUN_UPLOAD" == "1" ]]; then
    log "Uploading archive to ${REMOTE}:${REMOTE_DIR}/${ARCHIVE_BASENAME}"
    scp "$ARCHIVE_PATH" "${REMOTE}:${REMOTE_DIR}/"
  else
    log "Skipping upload; expecting ${REMOTE_DIR}/${ARCHIVE_BASENAME} on remote."
  fi

  log "Installing and validating on remote"
  ssh "$REMOTE" "bash -s" -- \
    "$REMOTE_DIR" \
    "$PROJECT_NAME" \
    "$ARCHIVE_BASENAME" \
    "$PYTHON_BIN" \
    "$CONDA_ENV" \
    "$TASK" \
    "$SMOKE_ENVS" \
    "$SMOKE_ITERS" \
    "$RUN_SMOKE" \
    "$GPU" \
    "$WANDB_MODE_VALUE" \
    "$RUN_ENV_FIX" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

REMOTE_DIR="$1"
PROJECT_NAME="$2"
ARCHIVE_BASENAME="$3"
PYTHON_BIN="$4"
CONDA_ENV="$5"
TASK="$6"
SMOKE_ENVS="$7"
SMOKE_ITERS="$8"
RUN_SMOKE="$9"
GPU="${10}"
WANDB_MODE_VALUE="${11}"
RUN_ENV_FIX="${12}"

log() {
  printf '\n[remote %s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

activate_conda_env() {
  local conda_env="$1"

  if [[ -z "$conda_env" ]]; then
    if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
      log "Using current conda environment: ${CONDA_DEFAULT_ENV}"
    fi
    return
  fi

  if [[ "${CONDA_DEFAULT_ENV:-}" == "$conda_env" ]]; then
    log "Conda environment already active: ${conda_env}"
    return
  fi

  log "Activating conda environment: ${conda_env}"
  if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
  elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
  else
    die "conda.sh not found under ~/miniconda3 or ~/anaconda3"
  fi

  if ! conda env list | awk '{print $1}' | grep -Fxq "$conda_env"; then
    printf 'Available conda environments:\n' >&2
    conda env list >&2
    die "conda environment not found: ${conda_env}"
  fi

  conda activate "$conda_env"
}

install_python_runtime_deps() {
  local python_bin="$1"
  local missing_packages

  missing_packages="$("$python_bin" - <<'PY'
import importlib.util

required = {
    "wandb": "wandb",
}

missing = [
    package
    for module, package in required.items()
    if importlib.util.find_spec(module) is None
]
print(" ".join(missing))
PY
)"

  if [[ -n "$missing_packages" ]]; then
    log "Installing missing Python runtime packages: ${missing_packages}"
    PIP_ROOT_USER_ACTION=ignore "$python_bin" -m pip install $missing_packages
  else
    log "Python runtime packages already available"
  fi
}

ensure_isaacgym_python_stack() {
  local python_bin="$1"

  if [[ "$RUN_ENV_FIX" != "1" ]]; then
    log "Skipping Python/PyTorch compatibility fix"
    return
  fi

  log "Checking Isaac Gym recommended Python stack"
  if "$python_bin" - <<'PY'
import importlib.util
import sys

expected = {
    "python": "3.8",
    "torch": "1.13.1",
    "cuda": "11.7",
    "numpy": "1.23",
}

py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
torch_ver = "missing"
torch_cuda = "missing"
numpy_ver = "missing"

if importlib.util.find_spec("torch") is not None:
    import torch
    torch_ver = torch.__version__
    torch_cuda = str(torch.version.cuda)
if importlib.util.find_spec("numpy") is not None:
    import numpy
    numpy_ver = numpy.__version__

print(f"python: {py_ver}")
print(f"torch: {torch_ver}")
print(f"torch cuda: {torch_cuda}")
print(f"numpy: {numpy_ver}")

ok = (
    py_ver == expected["python"]
    and torch_ver.startswith(expected["torch"])
    and torch_cuda.startswith(expected["cuda"])
    and numpy_ver.startswith(expected["numpy"])
)
raise SystemExit(0 if ok else 1)
PY
  then
    log "Python stack is compatible with Isaac Gym Preview 4"
    return
  fi

  command -v conda >/dev/null || die "conda is required to auto-fix Python/PyTorch/CUDA versions"

  log "Installing Isaac Gym recommended stack: Python 3.8, PyTorch 1.13.1, CUDA 11.7, NumPy 1.23.5"
  conda install -y \
    python=3.8 \
    numpy=1.23.5 \
    pytorch==1.13.1 \
    torchvision==0.14.1 \
    torchaudio==0.13.1 \
    pytorch-cuda=11.7 \
    -c pytorch \
    -c nvidia

  log "Re-checking Python stack"
  "$python_bin" - <<'PY'
import importlib.util
import sys

expected = {
    "python": "3.8",
    "torch": "1.13.1",
    "cuda": "11.7",
    "numpy": "1.23",
}

py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
if importlib.util.find_spec("torch") is None:
    raise SystemExit("torch is still missing after conda install")
if importlib.util.find_spec("numpy") is None:
    raise SystemExit("numpy is still missing after conda install")

import torch
import numpy

print(f"python: {py_ver}")
print(f"torch: {torch.__version__}")
print(f"torch cuda: {torch.version.cuda}")
print(f"numpy: {numpy.__version__}")

if py_ver != expected["python"]:
    raise SystemExit("python version check failed")
if not torch.__version__.startswith(expected["torch"]):
    raise SystemExit("torch version check failed")
if not str(torch.version.cuda).startswith(expected["cuda"]):
    raise SystemExit("torch cuda version check failed")
if not numpy.__version__.startswith(expected["numpy"]):
    raise SystemExit("numpy version check failed")
PY
}

activate_conda_env "$CONDA_ENV"
command -v "$PYTHON_BIN" >/dev/null || {
  printf 'ERROR: python executable not found: %s\n' "$PYTHON_BIN" >&2
  exit 1
}
ensure_isaacgym_python_stack "$PYTHON_BIN"

cd "$REMOTE_DIR"
[[ -f "$ARCHIVE_BASENAME" ]] || {
  printf 'ERROR: missing archive: %s/%s\n' "$REMOTE_DIR" "$ARCHIVE_BASENAME" >&2
  exit 1
}

if [[ -d "$PROJECT_NAME" ]]; then
  backup_name="${PROJECT_NAME}_bak_$(date +%Y%m%d_%H%M%S)"
  log "Backing up existing ${PROJECT_NAME} -> ${backup_name}"
  mv "$PROJECT_NAME" "$backup_name"
fi

log "Extracting ${ARCHIVE_BASENAME}"
tar -xzf "$ARCHIVE_BASENAME"
cd "$PROJECT_NAME"

log "Checking Python source files"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

bad = [str(p) for p in Path(".").rglob("*.py") if b"\0" in p.read_bytes()]
if bad:
    print("\n".join(bad))
    raise SystemExit("server copy check failed: source contains null bytes")
print("server copy ok: no null bytes")
PY

log "Checking GPU"
if command -v nvidia-smi >/dev/null; then
  nvidia-smi
else
  printf 'WARNING: nvidia-smi not found; continuing because some containers hide it.\n'
fi

log "Checking Isaac Gym and PyTorch"
"$PYTHON_BIN" --version
"$PYTHON_BIN" - <<'PY'
from isaacgym import gymapi
import torch

print("isaacgym ok")
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("torch cuda:", torch.version.cuda)
PY

log "Installing project in editable mode"
PIP_ROOT_USER_ACTION=ignore "$PYTHON_BIN" -m pip install -e .

install_python_runtime_deps "$PYTHON_BIN"

log "Checking task configuration"
"$PYTHON_BIN" - "$TASK" <<'PY'
import sys

import humanoid.envs
from humanoid.utils import task_registry

task = sys.argv[1]
env_cfg, _ = task_registry.get_cfgs(name=task)

checks = {
    "num_actions": env_cfg.env.num_actions,
    "num_single_obs": env_cfg.env.num_single_obs,
    "single_num_privileged_obs": env_cfg.env.single_num_privileged_obs,
    "default joints": len(env_cfg.init_state.default_joint_angles),
    "action scales": len(env_cfg.control.action_scale),
}

print("asset:", env_cfg.asset.file)
for key, value in checks.items():
    print(f"{key}: {value}")

expected = {
    "f1_dh_stand": {
        "num_actions": 29,
        "num_single_obs": 98,
        "single_num_privileged_obs": 141,
        "default joints": 29,
        "action scales": 29,
    }
}

if task in expected:
    mismatches = [
        f"{key}: expected {expected[task][key]}, got {value}"
        for key, value in checks.items()
        if expected[task][key] != value
    ]
    if mismatches:
        print("\n".join(mismatches))
        raise SystemExit("task config check failed")
PY

if [[ "$RUN_SMOKE" == "1" ]]; then
  log "Running headless smoke test"
  if [[ -n "$GPU" ]]; then
    export CUDA_VISIBLE_DEVICES="$GPU"
  fi
  export WANDB_MODE="$WANDB_MODE_VALUE"
  "$PYTHON_BIN" humanoid/scripts/train.py \
    --task="$TASK" \
    --headless \
    --num_envs="$SMOKE_ENVS" \
    --max_iterations="$SMOKE_ITERS"
else
  log "Skipping smoke test"
fi

log "Deployment validation finished"
printf '\nFormal training command:\n'
printf '  CUDA_VISIBLE_DEVICES=%s WANDB_MODE=%s %s humanoid/scripts/train.py --task=%s --headless --run_name=f1_29dof_v1\n' \
  "${GPU:-0}" "$WANDB_MODE_VALUE" "$PYTHON_BIN" "$TASK"
REMOTE_SCRIPT
}

if [[ "$RUN_PACKAGE" == "1" ]]; then
  package_project
else
  [[ -f "$ARCHIVE_PATH" ]] || die "archive does not exist: $ARCHIVE_PATH"
  log "Skipping package; using existing archive ${ARCHIVE_PATH}"
fi

if [[ "$PACKAGE_ONLY" == "1" ]]; then
  log "Package-only mode finished: ${ARCHIVE_PATH}"
  exit 0
fi

if [[ "$LOCAL_DEPLOY" == "1" ]]; then
  deploy_on_current_machine \
    "$REMOTE_DIR" \
    "$PROJECT_NAME" \
    "$ARCHIVE_PATH" \
    "$PYTHON_BIN" \
    "$CONDA_ENV" \
    "$TASK" \
    "$SMOKE_ENVS" \
    "$SMOKE_ITERS" \
    "$RUN_SMOKE" \
    "$GPU" \
    "$WANDB_MODE_VALUE"
  exit 0
fi

[[ -n "$REMOTE" ]] || die "--server is required unless --package-only is used"
remote_deploy
