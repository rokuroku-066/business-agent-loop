#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage: scripts/run_agent.sh <command> [options]

Commands:
  start              Initialize storage and seed tasks.
  status             Show current task and iteration status.
  record-iteration   Record a placeholder iteration log. Accepts --mode.
  step               Process a single task via the Harmony client. Accepts --mode.

This script activates the local .venv and forwards arguments to
`python -m business_agent_loop.cli` with sensible defaults:
  --base-dir   ${BASE_DIR:-$REPO_ROOT}
  --config-dir ${CONFIG_DIR:-$REPO_ROOT/config}

Additional arguments after the command are passed through to the CLI.
USAGE
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

COMMAND="$1"
shift

case "$COMMAND" in
  start|status|record-iteration|step)
    ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    usage
    exit 1
    ;;
esac

VENV_PATH="${REPO_ROOT}/.venv"
if [[ -d "$VENV_PATH" ]]; then
  # shellcheck disable=SC1091
  source "$VENV_PATH/bin/activate"
else
  echo "Warning: virtual environment not found at $VENV_PATH" >&2
fi

BASE_DIR="${BASE_DIR:-$REPO_ROOT}"
CONFIG_DIR="${CONFIG_DIR:-$REPO_ROOT/config}"

python -m business_agent_loop.cli \
  --base-dir "$BASE_DIR" \
  --config-dir "$CONFIG_DIR" \
  "$COMMAND" "$@"
