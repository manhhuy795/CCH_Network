# Design System Dashboard

## Token giao dien

- Spacing: `4, 8, 12, 16, 24, 32px`.
- Radius: `4, 6, 8px`; khong dung card bo tron lon.
- Typography: Segoe UI/system sans, body `13px`, heading `16-22px`.
- Shadow: chi dung shadow nhe cho drawer, dialog, menu va toast.
- Action chinh: xanh duong trung tinh.

## Trang thai

- Online/Allow/Success: xanh la, icon check va text.
- Offline/Deny/Drop/Error: do, icon loi va text.
- Warning/Degraded: cam, icon canh bao va text.
- Unknown/Disabled: xam, icon dau hoi va text.

Khong co trang thai nao chi duoc bieu dat bang mau.

## Component dung lai

- `StatusBadge`: status co icon va label.
- `FeedbackState`: empty, loading va error state.
- `ConfirmDialog`: xac nhan thao tac anh huong runtime.
- `Drawer`: inspector cho node/link va tro giup.
- `ToastRegion`: thong bao ngan, co the dong.
- `TaskProgress`: tien do va thoi gian tac vu.
- Button hierarchy: primary, secondary, danger va icon button.
- Form control: label ro rang, focus ring va error text.
- Data table: header sticky, filter va empty row.

## Accessibility

- Icon button luon co `title` hoac `aria-label`.
- Status luon co text.
- Dialog dung `role=dialog`, toast dung `aria-live`.
- Packet animation ton trong `prefers-reduced-motion`.
