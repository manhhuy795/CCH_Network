# Kien truc thong tin Dashboard

Dashboard phuc vu hai nhom chinh: IT Support va Network Administrator. Giao
dien uu tien desktop/laptop 1366x768, van mo rong tot tren man hinh NOC.

## Dieu huong chinh

Sidebar co sau muc, khong tao them nhieu cap:

1. Tong quan: suc khoe he thong va quick action.
2. Topology: so do, packet path, node/link inspector.
3. Kiem tra ket noi: Ping, TCP, UDP va Voice Quality.
4. Chinh sach & OpenFlow: policy, flow inventory va test theo cum.
5. Hieu nang: realtime metrics va lich su phep do.
6. Su kien & nhat ky: thao tac, canh bao va loi gan nhat.

## Header

Header luon hien thi ten he thong, trang thai tong, WebSocket, trang thai xac
thuc, tro giup va user menu. Token chi hien trong form dang nhap. Sau khi
backend xac nhan token, form token bien mat va duoc thay bang trang thai
`Da xac thuc`.

## Nguyen tac luong cong viec

- Mot chuc nang chi co mot vi tri chinh trong sidebar.
- Topology va packet animation duoc dung lai trong trang Topology va Kiem tra.
- Ket qua runtime den tu backend; frontend khong hardcode packet path.
- Trang thai loi phai co icon, text va error code, khong chi dung mau.
- Tac vu dai giu trang thai khi nguoi dung chuyen trang trong dashboard.
