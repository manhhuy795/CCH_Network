# Phase 49: Security Test Matrix

| Nhóm | Case | Kết quả cần đạt |
|---|---|---|
| Authentication | Thiếu session gọi runtime | 401 `AUTH_REQUIRED` |
| Authentication | Password sai | 401 `AUTH_INVALID`, có audit fail |
| Authentication | Đăng nhập đúng | 200, HttpOnly session, không trả password |
| Authentication | Session revoke/expiry | 401, không dùng lại session |
| CSRF | Cookie session thiếu header | 403 `CSRF_INVALID` |
| RBAC | viewer gọi ping | 403 `RBAC_FORBIDDEN` |
| RBAC | auditor gọi ping | 403 `RBAC_FORBIDDEN` |
| RBAC | operator gọi admin user API | 403 `RBAC_FORBIDDEN` |
| RBAC | admin tạo user/đổi role | 200 và audit success |
| Machine auth | operator token gọi runtime | Cho phép theo role operator |
| Machine auth | operator token gọi admin API | 403 |
| Logging | Sai auth | Không có password/session/token trong log |
| Network | WebSocket không có auth | Đóng 4401 |
| Browser | Frontend | `credentials: include`, không localStorage token, không token URL |

Các test live phải dùng backend/Mininet thật khi đo ping, iperf, flow hoặc link. Static test không được tuyên bố runtime PASS.
