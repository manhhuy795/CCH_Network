#!/usr/bin/env python3
"""Create the first admin without putting a password in argv or logs."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard" / "backend"))

from app import auth_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Tao admin Phase 49 an toan.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-stdin", action="store_true", help="Doc password tu stdin, khong hien thi.")
    args = parser.parse_args()

    auth_store.initialize()
    username = auth_store.validate_username(args.username)
    if any(user["username"] == username for user in auth_store.list_users()):
        print(f"Admin bootstrap khong thay doi: user {username} da ton tai.")
        return 0

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        confirmation = password
    else:
        password = getpass.getpass("Nhap mat khau admin (it nhat 12 ky tu): ")
        confirmation = getpass.getpass("Nhap lai mat khau admin: ")
    if password != confirmation:
        print("Mat khau xac nhan khong khop.", file=sys.stderr)
        return 2
    try:
        user = auth_store.create_user(username, password, "admin")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    auth_store.audit(action="bootstrap.admin", result="success", actor=user, detail={"username": username})
    print(f"Da tao admin {username}. Mat khau khong duoc ghi log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
