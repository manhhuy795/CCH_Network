#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR=""
OUTPUT=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --report-dir) shift; REPORT_DIR="$1" ;;
    --output) shift; OUTPUT="$1" ;;
    -h|--help) echo "Dung: phase48_failure_bundle.sh --report-dir <report> [--output <tar.gz>]"; exit 0 ;;
    *) echo "Tuy chon khong hop le: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$REPORT_DIR" in /*) ;; *) REPORT_DIR="$ROOT_DIR/$REPORT_DIR" ;; esac
case "$REPORT_DIR" in "$ROOT_DIR"/runtime_reports/phase48_final_acceptance_*) ;; *) echo "Chi chap nhan report Phase 48 trong runtime_reports/phase48_final_acceptance_*" >&2; exit 2 ;; esac
[ -d "$REPORT_DIR" ] || { echo "Khong thay report: $REPORT_DIR" >&2; exit 2; }
[ -n "$OUTPUT" ] || OUTPUT="$ROOT_DIR/runtime_reports/phase48_failure_bundle_$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
TMP_DIR="$(mktemp -d /tmp/cch-phase48-bundle.XXXXXX)"
cleanup() { find "$TMP_DIR" -type f -delete 2>/dev/null || true; rmdir "$TMP_DIR" 2>/dev/null || true; }
trap cleanup EXIT
mkdir -p "$TMP_DIR/report" "$TMP_DIR/environment"
python3 - "$REPORT_DIR" "$TMP_DIR/report" <<'PY'
from pathlib import Path
import re, sys
source, target = map(Path, sys.argv[1:])
blocked = {"operator.token", ".git-credentials", "id_rsa", "id_ed25519", "cookies.sqlite", "History", "browser"}
secret_name = re.compile(r"(token|password|secret|credential|private|\.pem$|\.key$)", re.I)
def redact_text(value: str) -> str:
    value = re.sub(r"(?i)(X-CCH-Operator-Token:\s*)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)(Authorization:\s*Bearer\s+)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:token|password|secret|passwd)\s*[:=]\s*)\S+", r"\1[REDACTED]", value)
    value = re.sub(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", "[PRIVATE_KEY_REDACTED]", value, flags=re.S)
    return value
for path in source.rglob("*"):
    if not path.is_file():
        continue
    rel = path.relative_to(source)
    if any(part in blocked or secret_name.search(part) for part in rel.parts):
        continue
    destination = target / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.write_text(redact_text(path.read_text(encoding="utf-8")), encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
PY
{
  date -u
  uname -a
  id
  python3 --version
  git -C "$ROOT_DIR" status --short --branch
  git -C "$ROOT_DIR" log -5 --oneline
  ss -ltn 2>&1 || true
  ip netns list 2>&1 || true
  sudo -n ovs-vsctl list-br 2>&1 || true
  sudo -n ovs-vsctl show 2>&1 || true
} > "$TMP_DIR/environment/system.txt"
mkdir -p "$(dirname "$OUTPUT")"
tar -czf "$OUTPUT" -C "$TMP_DIR" report environment
printf 'Failure bundle: %s\n' "$OUTPUT"
