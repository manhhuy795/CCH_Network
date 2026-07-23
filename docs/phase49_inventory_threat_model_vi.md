# Phase 49: Inventory và Threat Model

## Inventory trước khi sửa

- Backend FastAPI: `dashboard/backend/app/{main,api,security,models,activity}.py`.
- Runtime control: Mininet Control Agent, OVS, OS-Ken, operator token trong `logs/operator.token`.
- Frontend React/Vite: `dashboard/frontend/src/App.tsx`, API client và AppShell.
- Test: Python pytest và Vitest; Phase 44–48 đã có gate/report trong lịch sử main sau khi merge Phase 48.
- Trạng thái đầu Phase 49: main sạch tại `d6068ec`, branch `feature/phase49-auth-rbac`.

## Threats

1. Token runtime bị đưa vào browser, log hoặc URL.
2. Người dùng viewer gọi thẳng API runtime dù frontend đã ẩn nút.
3. Session bị dùng lại sau logout/expiry.
4. CSRF trên cookie session cho link fail, policy toggle hoặc user management.
5. Login brute force.
6. CORS wildcard hoặc WebSocket không xác thực.
7. Audit log làm lộ password/cookie/token.

## Controls

PBKDF2 password hash, opaque session hash, TTL/revoke/rotation, CSRF double-submit, role enforcement server-side, rate limit login, CORS allowlist, WebSocket handshake auth, audit sanitize và runtime DB/log bị Git ignore.
