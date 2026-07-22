# Phase 49: Ma trận RBAC

| Chức năng | admin | operator | viewer | auditor |
|---|---:|---:|---:|---:|
| Đăng nhập, xem phiên của mình | Có | Có | Có | Có |
| Health/auth status public | Có | Có | Có | Có |
| Đọc topology, policy, flow, metrics, firewall | Có | Có | Có | Có |
| Ping thật | Có | Có | Không | Không |
| TCP/UDP iperf | Có | Có | Không | Không |
| Voice Quality | Có | Có | Không | Không |
| Link fail/recover | Có | Có | Không | Không |
| Policy toggle vận hành | Có | Có | Không | Không |
| Xem activity vận hành | Có | Có | Không | Có qua audit |
| Xem audit/security log | Có | Không | Không | Có |
| Tạo user | Có | Không | Không | Không |
| Đổi role/disable/reset password | Có | Không | Không | Không |

## Nguyên tắc enforcement

- Backend là policy enforcement point; ẩn nút trên frontend không tạo quyền.
- Không xác thực trả `401 AUTH_REQUIRED` hoặc `AUTH_EXPIRED`.
- Có phiên nhưng sai quyền trả `403 RBAC_FORBIDDEN`.
- Operator token là principal role `operator`, không bao giờ là `admin`.
- CSRF áp dụng cho cookie session trên mọi request thay đổi trạng thái.
