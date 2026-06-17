#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot entry point for a fresh Gradmotion GUI cloud desktop.
# It installs the Codex public key, optionally bootstraps this training
# checkout, then keeps a reverse SSH tunnel open through a fixed ECS jump host.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BOOTSTRAP_SCRIPT="${SCRIPT_DIR}/bootstrap-gui-desktop.sh"
PUBLIC_KEY_FILE="${CODEX_TUNNEL_PUBLIC_KEY_FILE:-${SCRIPT_DIR}/codex_gradmotion.pub}"

ECS_HOST="${CODEX_TUNNEL_ECS_HOST:-121.40.166.191}"
ECS_USER="${CODEX_TUNNEL_ECS_USER:-root}"
REMOTE_PORT="${CODEX_TUNNEL_REMOTE_PORT:-2222}"
REMOTE_BIND="${CODEX_TUNNEL_REMOTE_BIND:-}"
LOCAL_HOST="${CODEX_TUNNEL_LOCAL_HOST:-localhost}"
LOCAL_PORT="${CODEX_TUNNEL_LOCAL_PORT:-22}"
STRICT_HOST_KEY="${CODEX_TUNNEL_STRICT_HOST_KEY:-accept-new}"
CONDA_ENV="${CONDA_ENV:-pointfoot_legged_gym}"
CONDA_AUTO_ACTIVATE="${CONDA_AUTO_ACTIVATE:-1}"

DO_BOOTSTRAP="${DO_BOOTSTRAP:-1}"
BOOTSTRAP_MUST_PASS="${BOOTSTRAP_MUST_PASS:-0}"
BOOTSTRAP_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  bash ops/gradmotion/start-codex-tunnel.sh [options] [-- bootstrap args]

Default flow:
  1. Add ops/gradmotion/codex_gradmotion.pub to /root/.ssh/authorized_keys.
  2. Run ops/gradmotion/bootstrap-gui-desktop.sh.
  3. Start a reverse SSH tunnel to the fixed ECS jump host and keep it open.

Options:
  --remote-port PORT       Remote ECS port for this Gradmotion desktop. Default: 2222.
  --ecs-host HOST          ECS public host/IP. Default comes from the project script.
  --ecs-user USER          ECS SSH user. Default: root.
  --remote-bind ADDR       Remote bind address, for example 0.0.0.0.
  --no-bootstrap           Skip environment bootstrap and only start the tunnel.
  --bootstrap-must-pass    Do not start the tunnel if bootstrap fails.
  -h, --help               Show this help.

Environment overrides:
  CODEX_TUNNEL_ECS_HOST=121.40.166.191
  CODEX_TUNNEL_ECS_USER=root
  CODEX_TUNNEL_REMOTE_PORT=2222
  CODEX_TUNNEL_REMOTE_BIND=
  CODEX_TUNNEL_PUBLIC_KEY_FILE=ops/gradmotion/codex_gradmotion.pub
  CONDA_ENV=pointfoot_legged_gym
  CONDA_AUTO_ACTIVATE=1
  DO_BOOTSTRAP=1
  BOOTSTRAP_MUST_PASS=0

Examples:
  bash ops/gradmotion/start-codex-tunnel.sh
  bash ops/gradmotion/start-codex-tunnel.sh --remote-port 2223
  bash ops/gradmotion/start-codex-tunnel.sh --no-bootstrap --remote-port 2224
  bash ops/gradmotion/start-codex-tunnel.sh -- --skip-gui-smoke
EOF
}

log() {
  printf '[codex-tunnel] %s\n' "$*"
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

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --remote-port)
        REMOTE_PORT="${2:?Missing value for --remote-port}"
        shift 2
        ;;
      --ecs-host)
        ECS_HOST="${2:?Missing value for --ecs-host}"
        shift 2
        ;;
      --ecs-user)
        ECS_USER="${2:?Missing value for --ecs-user}"
        shift 2
        ;;
      --remote-bind)
        REMOTE_BIND="${2:?Missing value for --remote-bind}"
        shift 2
        ;;
      --no-bootstrap)
        DO_BOOTSTRAP=0
        shift
        ;;
      --bootstrap-must-pass)
        BOOTSTRAP_MUST_PASS=1
        shift
        ;;
      --)
        shift
        BOOTSTRAP_ARGS+=("$@")
        break
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
  done
}

require_root() {
  if [[ "$(id -u)" != "0" ]]; then
    echo "Run this script as root so it can authorize root SSH access for Codex." >&2
    exit 1
  fi
}

install_codex_public_key() {
  if [[ ! -f "${PUBLIC_KEY_FILE}" ]]; then
    echo "Missing Codex public key file: ${PUBLIC_KEY_FILE}" >&2
    exit 1
  fi

  local public_key
  public_key="$(sed -n '1p' "${PUBLIC_KEY_FILE}")"
  if [[ -z "${public_key}" ]]; then
    echo "Codex public key file is empty: ${PUBLIC_KEY_FILE}" >&2
    exit 1
  fi

  mkdir -p /root/.ssh
  chmod 700 /root/.ssh
  touch /root/.ssh/authorized_keys

  if grep -Fqx "${public_key}" /root/.ssh/authorized_keys; then
    log "Codex public key already exists in /root/.ssh/authorized_keys"
  else
    printf '%s\n' "${public_key}" >> /root/.ssh/authorized_keys
    log "Added Codex public key to /root/.ssh/authorized_keys"
  fi

  chmod 600 /root/.ssh/authorized_keys
}

ensure_local_sshd() {
  if command -v ss >/dev/null 2>&1 && ss -lnt | awk '$4 ~ /(^|:|\])22$/ { found=1 } END { exit found ? 0 : 1 }'; then
    log "Local SSH service is listening on port 22"
    return
  fi

  log "Local SSH service is not listening on port 22; trying to start it"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl start ssh 2>/dev/null || true
  fi
  if command -v service >/dev/null 2>&1; then
    service ssh start 2>/dev/null || true
  fi

  if command -v ss >/dev/null 2>&1 && ss -lnt | awk '$4 ~ /(^|:|\])22$/ { found=1 } END { exit found ? 0 : 1 }'; then
    log "Local SSH service is listening on port 22"
  else
    echo "Local SSH service is still not listening on port 22; cannot create a useful reverse tunnel." >&2
    exit 1
  fi
}

run_bootstrap() {
  if [[ "${DO_BOOTSTRAP}" != "1" ]]; then
    log "Skipping bootstrap because DO_BOOTSTRAP=0"
    return
  fi

  if [[ ! -f "${BOOTSTRAP_SCRIPT}" ]]; then
    echo "Missing bootstrap script: ${BOOTSTRAP_SCRIPT}" >&2
    exit 1
  fi

  log "Running Gradmotion GUI bootstrap before opening the tunnel"
  if bash "${BOOTSTRAP_SCRIPT}" "${BOOTSTRAP_ARGS[@]}"; then
    log "Bootstrap finished"
  else
    local status=$?
    if [[ "${BOOTSTRAP_MUST_PASS}" == "1" ]]; then
      echo "Bootstrap failed with exit code ${status}; not opening tunnel." >&2
      exit "${status}"
    fi
    log "Bootstrap failed with exit code ${status}; opening tunnel anyway so Codex can debug"
  fi
}

start_reverse_tunnel() {
  local reverse_spec
  if [[ -n "${REMOTE_BIND}" ]]; then
    reverse_spec="${REMOTE_BIND}:${REMOTE_PORT}:${LOCAL_HOST}:${LOCAL_PORT}"
  else
    reverse_spec="${REMOTE_PORT}:${LOCAL_HOST}:${LOCAL_PORT}"
  fi

  log "Starting reverse SSH tunnel"
  log "ECS: ${ECS_USER}@${ECS_HOST}"
  log "Remote forward: ${reverse_spec}"
  log "Keep this terminal open. Press Ctrl-C to close the tunnel."

  exec ssh \
    -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking="${STRICT_HOST_KEY}" \
    -R "${reverse_spec}" \
    "${ECS_USER}@${ECS_HOST}"
}

main() {
  parse_args "$@"
  require_root
  cd "${REPO_ROOT}"

  log "Repository: ${REPO_ROOT}"
  log "Public key file: ${PUBLIC_KEY_FILE}"
  log "Remote port: ${REMOTE_PORT}"

  activate_conda_env
  install_codex_public_key
  ensure_local_sshd
  run_bootstrap
  start_reverse_tunnel
}

main "$@"
