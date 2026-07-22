# Phase 48: Runbook nghiệm thu cuối trên Ubuntu

## Mục đích

Phase 48 là cổng nghiệm thu cuối cho mô hình Hybrid MPLS L3VPN Logic Simulation + SDN Edge Policy. Đây là kiểm thử runtime thật trên Ubuntu, Mininet, Open vSwitch, OS-Ken, FastAPI và React. Không dùng dữ liệu giả để kết luận PASS.

## Điều kiện

    cd /home/huy/Downloads/CCH_Network
    git status --short
    git switch feature/phase48-final-ubuntu-acceptance

Topology phải đang chạy bằng /usr/bin/python3 cho Mininet. Backend, frontend và controller có thể được khởi động bằng script dự án. Token operator chỉ đọc từ logs/operator.token; không dán token vào terminal log.

## Các mode của gate

    bash scripts/phase48_final_ubuntu_acceptance.sh preflight
    bash scripts/phase48_final_ubuntu_acceptance.sh static
    sudo -n bash scripts/phase48_final_ubuntu_acceptance.sh runtime --reuse-running
    sudo -n bash scripts/phase48_final_ubuntu_acceptance.sh full --reuse-running
    bash scripts/phase48_final_ubuntu_acceptance.sh clean-clone --clean-clone-dir /tmp/cch-phase48-clean

--start-missing chỉ dùng khi operator đã chủ động xác nhận việc khởi động các thành phần còn thiếu. --keep-running dành cho wrapper vận hành; gate không tự dừng topology đang được tái sử dụng.

## Runtime bắt buộc

Kiểm tra controller 6653, backend 8000, frontend 5173, namespace Mininet, socket Control Agent HEALTH, 9 OVS bridge, 2 firewall namespace, flow OpenFlow 1.3, dashboard health, ping allow/deny, firewall counter, dashboard smoke, link fail/recover và log lỗi transport.

Các bài đo phải lấy kết quả từ API/runtime thật. Khi policy DENY, response phải giữ đúng contract DENY/POLICY_DENIED, không biến thành lỗi server.

## Failure bundle

Khi gate FAIL:

    bash scripts/phase48_failure_bundle.sh --report-dir runtime_reports/phase48_final_acceptance_<UTC>

Bundle chỉ lấy report đã tạo, snapshot hệ thống tối thiểu và git metadata. Script bỏ qua token, mật khẩu, credential, private key, cookie và browser data. Không đọc ~/.git-credentials, khóa SSH riêng hoặc toàn bộ home.

## Quy tắc kết luận

- PASS: mọi case trong mode đều PASS và có artifact/manifest.
- FAIL: có lệnh thật chạy nhưng kết quả sai.
- BLOCKED: thiếu dependency, quyền hoặc runtime nên chưa thể kiểm chứng.
- Không đổi expected result để biến FAIL thành PASS.
- Không chạy Phase 49 trong Phase 48.
