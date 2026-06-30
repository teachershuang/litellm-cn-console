#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${APP_DIR}/logs"
LITELLM_ENV_FILE="${LITELLM_ENV_FILE:-/home/ls/F4T/LiteLLM/litellm/env.litellm}"

if [ -f "${LITELLM_ENV_FILE}" ]; then
  # shellcheck disable=SC1090
  source "${LITELLM_ENV_FILE}"
fi

if [ -f "${APP_DIR}/env.simple_ui" ]; then
  # shellcheck disable=SC1091
  source "${APP_DIR}/env.simple_ui"
fi

PORT="${SIMPLE_UI_PORT:-4040}"
PYTHON_BIN="${SIMPLE_UI_PYTHON_BIN:-python}"

mkdir -p "${LOG_DIR}"

if pgrep -af "uvicorn app:app --host 0.0.0.0 --port ${PORT}" >/dev/null 2>&1; then
  echo "LiteLLM CN Console is already running on port ${PORT}"
  exit 0
fi

cd "${APP_DIR}"
nohup "${PYTHON_BIN}" -m uvicorn app:app --host 0.0.0.0 --port "${PORT}" > "${LOG_DIR}/simple_cn_ui.log" 2>&1 &

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "LiteLLM CN Console is ready on http://0.0.0.0:${PORT}"
    exit 0
  fi
  sleep 2
done

echo "LiteLLM CN Console failed to start on port ${PORT}" >&2
exit 1
