#!/usr/bin/env python3
"""Documentation-link and tracked-secret checks for repository validation."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"(?i)\bpassword\s*[:=]\s*[A-Za-z0-9+/=_-]{16,}"),
    re.compile(r"CCH_DASHBOARD_OPERATOR_TOKEN\s*=\s*[A-Za-z0-9_-]{20,}"),
)


def docs_reference_errors(root: Path = ROOT_DIR) -> list[str]:
    """Return broken relative Markdown links under docs/."""
    errors: list[str] = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in sorted(root.glob("docs/**/*.md")):
        for target in pattern.findall(document.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (document.parent / target).resolve().exists():
                errors.append(f"{document.relative_to(root).as_posix()} -> {target}")
    return errors


def secret_scan(root: Path = ROOT_DIR) -> list[str]:
    """Scan tracked UTF-8 text files for obvious committed secrets."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return [result.stderr.decode(errors="replace")]

    matches: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / os.fsdecode(raw)
        if not path.is_file():
            continue
        try:
            value = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            matches.append(str(path.relative_to(root)))
    return sorted(set(matches))


def _print_errors(label: str, errors: Iterable[str]) -> bool:
    values = list(errors)
    if not values:
        print(f"PASS: {label}")
        return True
    for error in values:
        print(f"FAIL: {label}: {error}")
    return False


def main() -> int:
    ok = _print_errors("documentation references", docs_reference_errors())
    ok &= _print_errors("tracked secret scan", secret_scan())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
