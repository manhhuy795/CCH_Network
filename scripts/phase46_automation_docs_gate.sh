#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
shift || true

case "$MODE" in
  all|source|static|automation)
    exec "$ROOT_DIR/scripts/phase47_full_regression_gate.sh" static "$@"
    ;;
  frontend)
    exec "$ROOT_DIR/scripts/phase47_full_regression_gate.sh" frontend "$@"
    ;;
  runtime)
    exec "$ROOT_DIR/scripts/phase47_full_regression_gate.sh" runtime "$@"
    ;;
  *)
    echo "Usage: $0 {all|source|static|automation|frontend|runtime}" >&2
    exit 2
    ;;
esac
