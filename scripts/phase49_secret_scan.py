#!/usr/bin/env python3
"""Fail only on likely literal credentials; never print matching source lines."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


LITERAL_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----"),
    re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._~+/-]{16,}"),
    re.compile(r"(?i)\b(?:password|secret|token)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def main(root: str) -> int:
    repo = Path(root).resolve()
    listed = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=False)
    if listed.returncode != 0:
        return listed.returncode
    findings: list[str] = []
    for raw_path in listed.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = repo / raw_path.decode("utf-8", errors="replace")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, 1):
            if any(marker in line for marker in ("$(", "os.getenv", "getenv(", "secrets.", "operator.token")):
                continue
            if any(pattern.search(line) for pattern in LITERAL_PATTERNS):
                findings.append(f"{path.relative_to(repo)}:{number}")
    for item in findings:
        print(item)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
