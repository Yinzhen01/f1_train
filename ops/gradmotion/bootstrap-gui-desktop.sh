#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot bootstrap for a fresh Gradmotion GUI cloud desktop.
# Default flow: git pull -> install -> check -> gui-single -> gui-smoke.
# Formal long training is opt-in via --train or DO_TRAIN=1.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GUI_HELPER="${SCRIPT_DIR}/gui-desktop-train.sh"

PYTHON_BIN="${PYTHON_BIN:-python}"
TASK="${TASK:-f1_dh_stand}"
WANDB_MODE="${WANDB_MODE:-offline}"
DISPLAY="${DISPLAY:-}"
CONDA_ENV="${CONDA_ENV:-pointfoot_legged_gym}"
CONDA_AUTO_ACTIVATE="${CONDA_AUTO_ACTIVATE:-1}"

DO_GIT_PULL="${DO_GIT_PULL:-1}"
DO_INSTALL="${DO_INSTALL:-1}"
DO_CHECK="${DO_CHECK:-1}"
DO_GUI_SINGLE="${DO_GUI_SINGLE:-1}"
DO_GUI_SMOKE="${DO_GUI_SMOKE:-1}"
DO_HEADLESS_SMOKE="${DO_HEADLESS_SMOKE:-0}"
DO_TRAIN="${DO_TRAIN:-0}"

GUI_SINGLE_ENVS="${GUI_SINGLE_ENVS:-1}"
GUI_SINGLE_ITERS="${GUI_SINGLE_ITERS:-10}"
GUI_SMOKE_ENVS="${GUI_SMOKE_ENVS:-16}"
GUI_SMOKE_ITERS="${GUI_SMOKE_ITERS:-10}"
HEADLESS_SMOKE_ENVS="${HEADLESS_SMOKE_ENVS:-64}"
HEADLESS_SMOKE_ITERS="${HEADLESS_SMOKE_ITERS:-20}"
TRAIN_ENVS="${TRAIN_ENVS:-4096}"
TRAIN_ITERS="${TRAIN_ITERS:-3000}"
RUN_NAME="${RUN_NAME:-}"

usage() {
  cat <<'EOF'
Usage:
  bash ops/gradmotion/bootstrap-gui-desktop.sh [options]

Default flow:
  1. git pull
  2. python -m pip install -e .
  3. check GPU / DISPLAY / Isaac Gym / torch / F1 task shape
  4. run gui-single smoke test
  5. run gui-smoke test

Options:
  --train                 Run formal headless training after smoke tests.
  --headless-smoke        Run a small headless smoke test after GUI smoke tests.
  --skip-pull             Skip git pull.
  --skip-install          Skip editable install.
  --skip-check            Skip environment check.
  --skip-gui-single       Skip 1-env viewer smoke test.
  --skip-gui-smoke        Skip 16-env viewer smoke test.
  -h, --help              Show this help.

Environment overrides:
  PYTHON_BIN=python
  CONDA_ENV=pointfoot_legged_gym
  CONDA_AUTO_ACTIVATE=1
  TASK=f1_dh_stand
  WANDB_MODE=offline
  DISPLAY=:1
  GUI_SINGLE_ENVS=1
  GUI_SINGLE_ITERS=10
  GUI_SMOKE_ENVS=16
  GUI_SMOKE_ITERS=10
  HEADLESS_SMOKE_ENVS=64
  HEADLESS_SMOKE_ITERS=20
  TRAIN_ENVS=4096
  TRAIN_ITERS=3000
  RUN_NAME=f1_29dof_v1

Examples:
  bash ops/gradmotion/bootstrap-gui-desktop.sh
  bash ops/gradmotion/bootstrap-gui-desktop.sh --headless-smoke
  RUN_NAME=f1_29dof_v1 bash ops/gradmotion/bootstrap-gui-desktop.sh --train
EOF
}

log() {
  printf '[gradmotion-bootstrap] %s\n' "$*"
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

run_step() {
  log "==> $*"
  "$@"
}

helper() {
  PYTHON_BIN="${PYTHON_BIN}" \
  TASK="${TASK}" \
  WANDB_MODE="${WANDB_MODE}" \
  DISPLAY="${DISPLAY}" \
  bash "${GUI_HELPER}" "$@"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --train)
        DO_TRAIN=1
        ;;
      --headless-smoke)
        DO_HEADLESS_SMOKE=1
        ;;
      --skip-pull)
        DO_GIT_PULL=0
        ;;
      --skip-install)
        DO_INSTALL=0
        ;;
      --skip-check)
        DO_CHECK=0
        ;;
      --skip-gui-single)
        DO_GUI_SINGLE=0
        ;;
      --skip-gui-smoke)
        DO_GUI_SMOKE=0
        ;;
      -h|--help|help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage >&2
        exit 2
        ;;
    esac
    shift
  done
}

main() {
  parse_args "$@"

  cd "${REPO_ROOT}"
  if [[ ! -f "${GUI_HELPER}" ]]; then
    echo "Missing helper script: ${GUI_HELPER}" >&2
    exit 1
  fi

  activate_conda_env
  export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
  export DISPLAY

  log "Repository: ${REPO_ROOT}"
  log "Task: ${TASK}"
  log "Python: ${PYTHON_BIN}"
  log "DISPLAY=${DISPLAY}"
  log "WANDB_MODE=${WANDB_MODE}"

  if [[ "${DO_GIT_PULL}" == "1" ]]; then
    run_step git pull --ff-only
  fi

  if [[ "${DO_INSTALL}" == "1" ]]; then
    run_step helper install
  fi

  if [[ "${DO_CHECK}" == "1" ]]; then
    run_step helper check
  fi

  if [[ "${DO_GUI_SINGLE}" == "1" ]]; then
    log "Starting 1-env viewer smoke test"
    NUM_ENVS="${GUI_SINGLE_ENVS}" MAX_ITERATIONS="${GUI_SINGLE_ITERS}" \
      helper gui-single
  fi

  if [[ "${DO_GUI_SMOKE}" == "1" ]]; then
    log "Starting ${GUI_SMOKE_ENVS}-env viewer smoke test"
    NUM_ENVS="${GUI_SMOKE_ENVS}" MAX_ITERATIONS="${GUI_SMOKE_ITERS}" \
      helper gui-smoke
  fi

  if [[ "${DO_HEADLESS_SMOKE}" == "1" ]]; then
    log "Starting headless smoke test"
    NUM_ENVS="${HEADLESS_SMOKE_ENVS}" MAX_ITERATIONS="${HEADLESS_SMOKE_ITERS}" \
      helper headless-smoke
  fi

  if [[ "${DO_TRAIN}" == "1" ]]; then
    log "Starting formal headless training"
    NUM_ENVS="${TRAIN_ENVS}" MAX_ITERATIONS="${TRAIN_ITERS}" RUN_NAME="${RUN_NAME}" \
      helper train
  else
    log "Bootstrap complete. Formal training was not started."
    log "To start training: RUN_NAME=f1_29dof_v1 bash ops/gradmotion/bootstrap-gui-desktop.sh --train"
  fi
}

main "$@"
