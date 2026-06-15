#!/usr/bin/env bash
set -Eeuo pipefail

# Helper for interactive Gradmotion cloud desktops with Isaac Gym viewer.
# Run from the repository root or from any directory inside this checkout.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TASK="${TASK:-f1_dh_stand}"
WANDB_MODE="${WANDB_MODE:-offline}"
PYTHON_BIN="${PYTHON_BIN:-python}"
TENSORBOARD_PORT="${TENSORBOARD_PORT:-6006}"

usage() {
  cat <<'EOF'
Usage:
  bash ops/gradmotion/gui-desktop-train.sh <command> [extra train/play args]

Commands:
  check             Check DISPLAY, GPU, Isaac Gym, PyTorch, and F1 task shape.
  gui-smoke         Run Isaac Gym viewer smoke test. Default: NUM_ENVS=16 MAX_ITERATIONS=10.
  gui-single        Run the lightest viewer smoke test. Default: NUM_ENVS=1 MAX_ITERATIONS=10.
  headless-smoke    Run a small headless smoke test. Default: NUM_ENVS=64 MAX_ITERATIONS=20.
  train             Run formal headless training. Default: NUM_ENVS=4096 MAX_ITERATIONS=3000.
  tensorboard       Start TensorBoard for logs/f1_dh_stand.
  play              Replay a trained run with viewer. Set LOAD_RUN=<run_name> or pass run name.

Environment overrides:
  TASK=f1_dh_stand
  NUM_ENVS=16
  MAX_ITERATIONS=10
  RUN_NAME=f1_29dof_gui_smoke
  LOAD_RUN=<run_name>
  CUDA_VISIBLE_DEVICES=0
  WANDB_MODE=offline
  DISPLAY=:0
  PYTHON_BIN=python
  TENSORBOARD_PORT=6006

Examples:
  bash ops/gradmotion/gui-desktop-train.sh check
  bash ops/gradmotion/gui-desktop-train.sh gui-single
  NUM_ENVS=16 MAX_ITERATIONS=10 bash ops/gradmotion/gui-desktop-train.sh gui-smoke
  NUM_ENVS=4096 MAX_ITERATIONS=3000 RUN_NAME=f1_29dof_v1 bash ops/gradmotion/gui-desktop-train.sh train
  LOAD_RUN=f1_29dof_v1 bash ops/gradmotion/gui-desktop-train.sh play
  bash ops/gradmotion/gui-desktop-train.sh tensorboard
EOF
}

log() {
  printf '[gradmotion-gui] %s\n' "$*"
}

ensure_repo_root() {
  cd "${REPO_ROOT}"
  if [[ ! -f "humanoid/scripts/train.py" ]]; then
    echo "Cannot find humanoid/scripts/train.py under ${REPO_ROOT}" >&2
    exit 1
  fi
}

ensure_display() {
  if [[ -z "${DISPLAY:-}" ]]; then
    export DISPLAY=":0"
    log "DISPLAY was empty; using DISPLAY=:0"
  else
    log "DISPLAY=${DISPLAY}"
  fi
}

show_basic_env() {
  log "Repository: ${REPO_ROOT}"
  log "Task: ${TASK}"
  log "Python: ${PYTHON_BIN}"
  log "WANDB_MODE=${WANDB_MODE}"
  log "DISPLAY=${DISPLAY:-<empty>}"

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi
  else
    log "nvidia-smi not found"
  fi
}

check_python_env() {
  "${PYTHON_BIN}" - <<'PY'
from isaacgym import gymapi
import torch

print("isaacgym ok")
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("torch cuda:", torch.version.cuda)
PY
}

check_task_shape() {
  "${PYTHON_BIN}" - <<PY
import humanoid.envs
from humanoid.utils import task_registry

task = "${TASK}"
env_cfg, _ = task_registry.get_cfgs(name=task)
print("task:", task)
print("asset:", env_cfg.asset.file)
print("num_actions:", env_cfg.env.num_actions)
print("num_single_obs:", env_cfg.env.num_single_obs)
print("single_num_privileged_obs:", env_cfg.env.single_num_privileged_obs)
print("default joints:", len(env_cfg.init_state.default_joint_angles))
print("action scales:", len(env_cfg.control.action_scale))
PY
}

check_all() {
  ensure_repo_root
  show_basic_env
  check_python_env
  check_task_shape
}

default_run_name() {
  local suffix="$1"
  date +"f1_29dof_${suffix}_%Y%m%d_%H%M%S"
}

run_train() {
  local mode="$1"
  local default_envs="$2"
  local default_iterations="$3"
  local default_name_suffix="$4"
  shift 4

  ensure_repo_root

  local num_envs="${NUM_ENVS:-${default_envs}}"
  local max_iterations="${MAX_ITERATIONS:-${default_iterations}}"
  local run_name="${RUN_NAME:-$(default_run_name "${default_name_suffix}")}"
  local cmd=(
    "${PYTHON_BIN}" "humanoid/scripts/train.py"
    "--task=${TASK}"
    "--num_envs=${num_envs}"
    "--max_iterations=${max_iterations}"
    "--run_name=${run_name}"
  )

  if [[ "${mode}" == "headless" ]]; then
    cmd+=("--headless")
  else
    ensure_display
  fi

  log "Starting ${mode} training: num_envs=${num_envs}, max_iterations=${max_iterations}, run_name=${run_name}"
  WANDB_MODE="${WANDB_MODE}" "${cmd[@]}" "$@"
}

run_tensorboard() {
  ensure_repo_root
  log "Starting TensorBoard at http://localhost:${TENSORBOARD_PORT}"
  tensorboard --logdir logs/f1_dh_stand --host 0.0.0.0 --port "${TENSORBOARD_PORT}"
}

run_play() {
  ensure_repo_root
  ensure_display

  local load_run="${LOAD_RUN:-${1:-}}"
  if [[ -z "${load_run}" ]]; then
    echo "Set LOAD_RUN=<run_name> or pass the run name after 'play'." >&2
    exit 1
  fi
  shift || true

  log "Starting viewer replay for load_run=${load_run}"
  WANDB_MODE="${WANDB_MODE}" "${PYTHON_BIN}" humanoid/scripts/play.py \
    "--task=${TASK}" \
    "--load_run=${load_run}" \
    "$@"
}

main() {
  local command="${1:-gui-smoke}"
  if [[ $# -gt 0 ]]; then
    shift
  fi

  case "${command}" in
    -h|--help|help)
      usage
      ;;
    check)
      check_all
      ;;
    gui-smoke)
      run_train "gui" "16" "10" "gui_smoke" "$@"
      ;;
    gui-single)
      run_train "gui" "1" "10" "gui_single" "$@"
      ;;
    headless-smoke)
      run_train "headless" "64" "20" "headless_smoke" "$@"
      ;;
    train)
      run_train "headless" "4096" "3000" "train" "$@"
      ;;
    tensorboard)
      run_tensorboard
      ;;
    play)
      run_play "$@"
      ;;
    *)
      echo "Unknown command: ${command}" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
