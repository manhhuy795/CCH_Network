# Phase 49: Thiết kế Authentication

## Phạm vi

Dashboard dùng human authentication cho người vận hành và giữ operator token như một kênh machine-to-machine riêng cho script runtime. Frontend không lưu hoặc hiển thị operator token.

## Luồng đăng nhập

1. `POST /api/auth/login` nhận username/password qua HTTPS hoặc localhost.
2. Backend kiểm tra PBKDF2-HMAC-SHA256 trong SQLite runtime.
3. Backend tạo session ID ngẫu nhiên, chỉ lưu SHA-256 của session ID.
4. Session ID trả bằng cookie `HttpOnly`, `SameSite=Lax`; cookie `Secure` bật bằng `CCH_AUTH_COOKIE_SECURE=1`.
5. CSRF token nằm trong cookie không HttpOnly và phải được gửi lại bằng `X-CCH-CSRF` cho POST/PATCH/DELETE.
6. `GET /api/auth/me` là nguồn xác nhận phiên hiện tại.
7. Refresh xoay session cũ; logout revoke session và xóa cookie.

## Lưu trữ

- DB mặc định: `logs/auth.sqlite3`, đã nằm trong `.gitignore`.
- Schema tự migrate bằng `CREATE TABLE IF NOT EXISTS`.
- Password không bao giờ lưu plaintext.
- Session token, password và Authorization không được ghi audit/log.
- Có failed-attempt counter và khóa tạm thời sau 5 lần sai trong 15 phút.

## API contract

- `POST /api/auth/login`: 200 hoặc 401/429.
- `GET /api/auth/me`: 200 hoặc 401.
- `POST /api/auth/refresh`: 200 hoặc 401.
- `POST /api/auth/logout`: 200; request cookie session phải có CSRF hợp lệ.
- `GET /api/health` và `GET /api/auth/status` public để health check/login bootstrap.
- Topology, policy, flow, live status yêu cầu `dashboard.read`.
- Runtime yêu cầu `runtime.execute`; admin API yêu cầu role admin.

## Operator token

`CCH_DASHBOARD_OPERATOR_TOKEN` chỉ được đọc ở backend hoặc script runtime qua `logs/operator.token`. Header này không phải human session, không cấp admin, không được đưa vào URL/frontend bundle.
