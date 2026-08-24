# Generated configs

Thư mục này không giữ lại candidate config của topology cũ sau khi chuyển sang enterprise v7.

Nguồn tạo config hiện tại là:

- `vars/network_model.yml`
- `vars/sites.yml`
- `vars/vlans.yml`
- `vars/routing.yml`
- `vars/interface_mapping.yml`
- `templates/`

Trước khi dùng generated config cho review/lab, chạy generator trên đúng branch v7 và kiểm tra static validation trước:

```bash
python3 scripts/validate_redesigned_topology.py
python3 scripts/generate_configs.py
```

Không commit lại file sinh từ VLAN 20/30/40/50/60/70 hoặc topology Project A/B/C cũ.

Lưu ý: template `ce_l2vpn_edge.j2` chỉ mô tả customer attachment circuit. Không tự sinh provider MPLS pseudowire/control-plane khi chưa có contract carrier/vendor cụ thể.
