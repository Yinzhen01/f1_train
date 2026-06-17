#!/usr/bin/env bash
set -Eeuo pipefail

# Helper for interactive Gradmotion cloud desktops with Isaac Gym viewer.
# Run from the repository root or from any directory inside this checkout.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

TASK="${TASK:-f1_dh_stand}"
WANDB_MODE="${WANDB_MODE:-offline}"
PYTHON_BIN="${PYTHON_BIN:-python}"
CONDA_ENV="${CONDA_ENV:-pointfoot_legged_gym}"
CONDA_AUTO_ACTIVATE="${CONDA_AUTO_ACTIVATE:-1}"
TENSORBOARD_PORT="${TENSORBOARD_PORT:-6006}"
GUI_USER="${GUI_USER:-}"
GUI_HOLD_LOG="${GUI_HOLD_LOG:-/tmp/codex_isaac_viewer_hold.log}"
GUI_HOLD_PID_FILE="${GUI_HOLD_PID_FILE:-/tmp/codex_isaac_viewer_hold.pid}"
GUI_HOLD_RUN_NAME="${GUI_HOLD_RUN_NAME:-codex_gui_viewer_hold}"

usage() {
  cat <<'EOF'
Usage:
  bash ops/gradmotion/gui-desktop-train.sh <command> [extra train/play args]

Commands:
  install           Install this checkout into the active Python environment.
  check             Check DISPLAY, GPU, Isaac Gym, PyTorch, and F1 task shape.
  gui-env           Print detected GUI DISPLAY/XAUTHORITY settings.
  open-app          Open a small GUI app on the cloud desktop. Default: xclock.
  gui-hold          Start a detached long-lived 1-env Isaac Gym viewer.
  gui-hold-focused  Start detached viewer with camera focused on VIEWER_FOCUS_ENV.
  stop-gui-hold     Stop the detached viewer started by gui-hold.
  gui-hold-status   Show detached viewer PID/log status.
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
  CONDA_ENV=pointfoot_legged_gym
  CONDA_AUTO_ACTIVATE=1
  DISPLAY=:0
  GUI_USER=<desktop_user>
  GUI_HOLD_LOG=/tmp/codex_isaac_viewer_hold.log
  GUI_HOLD_PID_FILE=/tmp/codex_isaac_viewer_hold.pid
  GUI_HOLD_RUN_NAME=codex_gui_viewer_hold
  VIEWER_FOCUS_ENV=0
  VIEWER_REL_POS=1.3,-1.2,1.1
  VIEWER_REL_LOOKAT=0,0,0.75
  TERMINATION_SUPPORT_RECT_MARGIN=0.10
  PYTHON_BIN=python
  TENSORBOARD_PORT=6006

Examples:
  bash ops/gradmotion/gui-desktop-train.sh install
  bash ops/gradmotion/gui-desktop-train.sh check
  bash ops/gradmotion/gui-desktop-train.sh gui-env
  bash ops/gradmotion/gui-desktop-train.sh open-app xclock
  bash ops/gradmotion/gui-desktop-train.sh gui-hold
  TASK=f1_dh_motion_imitation NUM_ENVS=10 bash ops/gradmotion/gui-desktop-train.sh gui-hold-focused
  bash ops/gradmotion/gui-desktop-train.sh stop-gui-hold
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

activate_conda_env() {
  if [[ "${CONDA_AUTO_ACTIVATE}" != "1" || -z "${CONDA_ENV}" ]]; then
    log "Skipping conda activation"
    return
  fi

  if [[ "${CONDA_DEFAULT_ENV:-}" == "${CONDA_ENV}" ]]; then
    log "Conda env already active: ${CONDA_ENV}"
    return
  fi

  local conda_sh=""
  local candidates=(
    "/root/miniconda3/etc/profile.d/conda.sh"
    "${HOME:-}/miniconda3/etc/profile.d/conda.sh"
    "${HOME:-}/anaconda3/etc/profile.d/conda.sh"
    "/opt/conda/etc/profile.d/conda.sh"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      conda_sh="${candidate}"
      break
    fi
  done

  if [[ -n "${conda_sh}" ]]; then
    # shellcheck disable=SC1090
    source "${conda_sh}"
  elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
  else
    log "Conda not found; continuing with current Python"
    return
  fi

  if conda activate "${CONDA_ENV}"; then
    log "Activated conda env: ${CONDA_ENV}"
  else
    log "Failed to activate conda env '${CONDA_ENV}'; continuing with current Python"
  fi
}

ensure_repo_root() {
  cd "${REPO_ROOT}"
  if [[ ! -f "humanoid/scripts/train.py" ]]; then
    echo "Cannot find humanoid/scripts/train.py under ${REPO_ROOT}" >&2
    exit 1
  fi
  export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
}

ensure_display() {
  local detected_display=""
  local detected_user=""

  if [[ -z "${DISPLAY:-}" ]]; then
    if command -v who >/dev/null 2>&1; then
      detected_display="$(
        who | awk 'match($0, /\(:[0-9]+(\.[0-9]+)?\)/) { print substr($0, RSTART + 1, RLENGTH - 2); exit }'
      )"
    fi

    if [[ -z "${detected_display}" && -d /tmp/.X11-unix ]]; then
      detected_display="$(
        find /tmp/.X11-unix -maxdepth 1 -type s -name 'X*' -printf '%f\n' 2>/dev/null \
          | sed 's/^X/:/' \
          | sort -V \
          | head -n 1
      )"
    fi

    export DISPLAY="${detected_display:-:0}"
    log "DISPLAY was empty; using DISPLAY=${DISPLAY}"
  else
    log "DISPLAY=${DISPLAY}"
  fi

  if [[ -z "${GUI_USER}" ]] && command -v who >/dev/null 2>&1; then
    detected_user="$(
      who | awk 'match($0, /\(:[0-9]+(\.[0-9]+)?\)/) { print $1; exit }'
    )"
    GUI_USER="${detected_user}"
  fi

  if [[ -z "${XAUTHORITY:-}" && -n "${GUI_USER}" ]] && command -v getent >/dev/null 2>&1; then
    local gui_home=""
    gui_home="$(getent passwd "${GUI_USER}" | cut -d: -f6 || true)"
    if [[ -n "${gui_home}" && -f "${gui_home}/.Xauthority" ]]; then
      export XAUTHORITY="${gui_home}/.Xauthority"
      log "XAUTHORITY=${XAUTHORITY}"
    fi
  elif [[ -n "${XAUTHORITY:-}" ]]; then
    log "XAUTHORITY=${XAUTHORITY}"
  fi
}

show_gui_env() {
  ensure_display
  log "GUI_USER=${GUI_USER:-<empty>}"
  log "DISPLAY=${DISPLAY:-<empty>}"
  log "XAUTHORITY=${XAUTHORITY:-<empty>}"
  if [[ -d /tmp/.X11-unix ]]; then
    ls -la /tmp/.X11-unix
  fi
}

open_gui_app() {
  ensure_display

  local app="${1:-xclock}"
  if [[ $# -gt 0 ]]; then
    shift
  fi

  log "Opening GUI app on the cloud desktop: ${app} $*"
  if [[ -n "${GUI_USER}" && "${GUI_USER}" != "$(id -un)" ]] && command -v runuser >/dev/null 2>&1; then
    runuser -u "${GUI_USER}" -- env DISPLAY="${DISPLAY}" XAUTHORITY="${XAUTHORITY:-}" setsid -f "${app}" "$@"
  else
    env DISPLAY="${DISPLAY}" XAUTHORITY="${XAUTHORITY:-}" setsid -f "${app}" "$@"
  fi
}

show_basic_env() {
  log "Repository: ${REPO_ROOT}"
  log "Task: ${TASK}"
  log "Python: ${PYTHON_BIN}"
  log "WANDB_MODE=${WANDB_MODE}"
  log "DISPLAY=${DISPLAY:-<empty>}"
  log "XAUTHORITY=${XAUTHORITY:-<empty>}"

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

check_required_python_modules() {
  "${PYTHON_BIN}" - <<'PY'
import importlib.util
import sys

missing = [
    name for name in ("wandb",)
    if importlib.util.find_spec(name) is None
]
if missing:
    print("Missing Python modules: " + ", ".join(missing), file=sys.stderr)
    print("Run one of these in the active cloud-desktop environment:", file=sys.stderr)
    print("  python -m pip install -e .", file=sys.stderr)
    print("  python -m pip install " + " ".join(missing), file=sys.stderr)
    sys.exit(2)

print("required Python modules ok")
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
  ensure_display
  show_basic_env
  check_python_env
  check_required_python_modules
  check_task_shape
}

install_project() {
  ensure_repo_root
  log "Installing ${REPO_ROOT} into the active Python environment"
  "${PYTHON_BIN}" -m pip install -e .
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
  check_required_python_modules

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
  PYTHONPATH="${PYTHONPATH}" WANDB_MODE="${WANDB_MODE}" "${cmd[@]}" "$@"
}

find_gui_hold_pids() {
  local run_name="${RUN_NAME:-${GUI_HOLD_RUN_NAME}}"
  pgrep -f "humanoid/scripts/train(_focused_view)?\\.py.*--run_name=${run_name}" || true
}

run_gui_hold_status() {
  local pids
  pids="$(find_gui_hold_pids)"
  log "GUI_HOLD_RUN_NAME=${RUN_NAME:-${GUI_HOLD_RUN_NAME}}"
  log "GUI_HOLD_PID_FILE=${GUI_HOLD_PID_FILE}"
  log "GUI_HOLD_LOG=${GUI_HOLD_LOG}"

  if [[ -f "${GUI_HOLD_PID_FILE}" ]]; then
    log "PID file: $(cat "${GUI_HOLD_PID_FILE}")"
  else
    log "PID file: <missing>"
  fi

  if [[ -n "${pids}" ]]; then
    log "Running detached viewer PID(s): ${pids//$'\n'/ }"
  else
    log "No detached viewer process found"
  fi

  if [[ -f "${GUI_HOLD_LOG}" ]]; then
    log "Last 20 log lines:"
    tail -n 20 "${GUI_HOLD_LOG}"
  fi
}

run_gui_hold() {
  local train_script="humanoid/scripts/train.py"
  local extra_args=("$@")
  run_gui_hold_with_script "${train_script}" "${extra_args[@]}"
}

run_gui_hold_focused() {
  local train_script="humanoid/scripts/train_focused_view.py"
  local extra_args=("$@")
  run_gui_hold_with_script "${train_script}" "${extra_args[@]}"
}

run_gui_hold_with_script() {
  local train_script="$1"
  shift
  local extra_args=("$@")

  ensure_repo_root
  ensure_display
  check_required_python_modules

  if [[ ! -f "${train_script}" ]]; then
    echo "Missing training script: ${train_script}" >&2
    exit 1
  fi

  local existing_pids
  existing_pids="$(find_gui_hold_pids)"
  if [[ -n "${existing_pids}" ]]; then
    log "Detached viewer already running: ${existing_pids//$'\n'/ }"
    log "Use 'stop-gui-hold' before starting another detached viewer with the same run name."
    return
  fi

  local num_envs="${NUM_ENVS:-1}"
  local max_iterations="${MAX_ITERATIONS:-100000}"
  local run_name="${RUN_NAME:-${GUI_HOLD_RUN_NAME}}"

  local cmd=(
    "${PYTHON_BIN}" "${train_script}"
    "--task=${TASK}"
    "--num_envs=${num_envs}"
    "--max_iterations=${max_iterations}"
    "--run_name=${run_name}"
  )
  cmd+=("${extra_args[@]}")

  log "Starting detached GUI viewer: num_envs=${num_envs}, max_iterations=${max_iterations}, run_name=${run_name}"
  log "Training script: ${train_script}"
  log "Log file: ${GUI_HOLD_LOG}"

  nohup env \
    PYTHONPATH="${PYTHONPATH}" \
    WANDB_MODE="${WANDB_MODE}" \
    DISPLAY="${DISPLAY}" \
    XAUTHORITY="${XAUTHORITY:-}" \
    VIEWER_FOCUS_ENV="${VIEWER_FOCUS_ENV:-0}" \
    VIEWER_REL_POS="${VIEWER_REL_POS:-1.3,-1.2,1.1}" \
    VIEWER_REL_LOOKAT="${VIEWER_REL_LOOKAT:-0,0,0.75}" \
    "${cmd[@]}" \
    >"${GUI_HOLD_LOG}" 2>&1 < /dev/null &

  local pid=$!
  printf '%s\n' "${pid}" > "${GUI_HOLD_PID_FILE}"
  sleep 1

  if kill -0 "${pid}" 2>/dev/null; then
    log "Detached viewer started with PID ${pid}"
  else
    echo "Detached viewer exited immediately. Log tail:" >&2
    tail -n 40 "${GUI_HOLD_LOG}" >&2 || true
    exit 1
  fi
}

stop_gui_hold() {
  local run_name="${RUN_NAME:-${GUI_HOLD_RUN_NAME}}"
  local stopped=0

  if [[ -f "${GUI_HOLD_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${GUI_HOLD_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      log "Stopping detached viewer PID ${pid}"
      kill "${pid}" 2>/dev/null || true
      stopped=1
    fi
    rm -f "${GUI_HOLD_PID_FILE}"
  fi

  local pids
  pids="$(find_gui_hold_pids)"
  if [[ -n "${pids}" ]]; then
    log "Stopping detached viewer process(es) for run_name=${run_name}: ${pids//$'\n'/ }"
    pkill -f "humanoid/scripts/train(_focused_view)?\\.py.*--run_name=${run_name}" || true
    stopped=1
  fi

  if [[ "${stopped}" == "1" ]]; then
    log "Detached viewer stop requested"
  else
    log "No detached viewer process found"
  fi
}

run_tensorboard() {
  ensure_repo_root
  log "Starting TensorBoard at http://localhost:${TENSORBOARD_PORT}"
  tensorboard --logdir logs/f1_dh_stand --host 0.0.0.0 --port "${TENSORBOARD_PORT}"
}

run_play() {
  ensure_repo_root
  ensure_display
  check_required_python_modules

  local load_run="${LOAD_RUN:-${1:-}}"
  if [[ -z "${load_run}" ]]; then
    echo "Set LOAD_RUN=<run_name> or pass the run name after 'play'." >&2
    exit 1
  fi
  shift || true

  log "Starting viewer replay for load_run=${load_run}"
  PYTHONPATH="${PYTHONPATH}" WANDB_MODE="${WANDB_MODE}" "${PYTHON_BIN}" humanoid/scripts/play.py \
    "--task=${TASK}" \
    "--load_run=${load_run}" \
    "$@"
}

main() {
  local command="${1:-gui-smoke}"
  if [[ $# -gt 0 ]]; then
    shift
  fi

  activate_conda_env

  case "${command}" in
    -h|--help|help)
      usage
      ;;
    check)
      check_all
      ;;
    install)
      install_project
      ;;
    gui-env)
      show_gui_env
      ;;
    open-app)
      open_gui_app "$@"
      ;;
    gui-hold)
      run_gui_hold "$@"
      ;;
    gui-hold-focused)
      run_gui_hold_focused "$@"
      ;;
    stop-gui-hold)
      stop_gui_hold
      ;;
    gui-hold-status)
      run_gui_hold_status
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
