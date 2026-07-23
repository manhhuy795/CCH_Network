# Phase 49: Vận hành bảo mật

## Bootstrap admin

Chạy từ root repository:

```bash
./scripts/phase49_bootstrap_admin.py
```

Script hỏi mật khẩu bằng prompt ẩn. Có thể dùng stdin trong automation, không truyền mật khẩu qua argv:

```bash
printf '%s\n' "$PASSWORD" | ./scripts/phase49_bootstrap_admin.py --username admin --password-stdin
```

Mật khẩu không được in vào log. Bootstrap idempotent: user đã tồn tại thì không đổi password.

## Chạy dashboard

```bash
./scripts/start_demo.sh --install
```

Mở frontend và đăng nhập bằng human account. Không nhập operator token vào trình duyệt.

## Biến môi trường an toàn

- `CCH_AUTH_DB`: đường dẫn DB runtime ngoài Git.
- `CCH_AUTH_SESSION_TTL_SECONDS`: TTL 300 đến 604800 giây.
- `CCH_AUTH_COOKIE_SECURE=1`: bắt buộc khi chạy HTTPS.
- `CCH_DASHBOARD_CORS_ORIGINS`: danh sách origin cụ thể, phân cách bằng dấu phẩy.
- `CCH_DASHBOARD_OPERATOR_TOKEN`: chỉ dành cho runtime script/backend.

## Xử lý sự cố

- `AUTH_REQUIRED`/`AUTH_EXPIRED`: đăng nhập lại.
- `AUTH_INVALID`: kiểm tra username/password, không đoán mật khẩu trong log.
- `AUTH_LOCKED`: chờ hết thời gian khóa hoặc admin xử lý chính sách tài khoản.
- `RBAC_FORBIDDEN`: kiểm tra role, không tắt auth để vượt quyền.
- `CSRF_INVALID`: refresh trang để nhận CSRF cookie mới.

## Artifact/log

Audit chỉ lưu actor, role, action, result, request ID, source IP và chi tiết đã sanitize. Không commit `logs/`, SQLite runtime, cookie jar, token, password, private key hoặc report chứa secret.
