import { X } from "lucide-react";

export default function Drawer({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="drawer-layer">
      <button className="drawer-scrim" aria-label="Đóng bảng chi tiết" onClick={onClose} />
      <aside className="drawer" aria-label={title}>
        <div className="drawer-header">
          <h2>{title}</h2>
          <button className="icon-button" title="Đóng" onClick={onClose}><X size={18} /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}
