import { AlertTriangle, X } from "lucide-react";

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Xác nhận",
  danger = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="dialog-title">
          <AlertTriangle size={18} aria-hidden="true" />
          <h2 id="confirm-title">{title}</h2>
          <button className="icon-button" title="Đóng" onClick={onClose}><X size={17} /></button>
        </div>
        <p>{message}</p>
        <div className="dialog-actions">
          <button onClick={onClose}>Hủy</button>
          <button className={danger ? "danger solid" : "primary"} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
