# Generated configs

Thư mục này không giữ lại candidate config của topology cũ sau khi chuyển sang enterprise v7.

Nguồn tạo config hiện tại là:

- `vars/network_model.yml`
- `vars/sites.yml`
- `vars/vlans.yml`
- `vars/routing.yml`
- `vars/interface_mapping.yml`
- `templates/`

Trước khi dùng generated config cho review/lab, chạy generator từ source of truth hiện hành và kiểm tra static validation trước:

```bash
python3 scripts/validate_topology.py
python3 scripts/generate_configs.py
```

Các file sinh trong thư mục này là runtime output và bị Git ignore; chỉ `README.md` cùng `.gitkeep` được track.

Lưu ý: template `ce_l2vpn_edge.j2` chỉ mô tả customer attachment circuit. Không tự sinh provider MPLS pseudowire/control-plane khi chưa có contract carrier/vendor cụ thể.
