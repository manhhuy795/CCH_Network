import { AlertTriangle, CheckCircle2, CircleHelp, XCircle } from "lucide-react";

export type StatusTone = "online" | "offline" | "degraded" | "unknown";

const config = {
  online: { icon: CheckCircle2, label: "Đang phản hồi" },
  offline: { icon: XCircle, label: "Mất phản hồi" },
  degraded: { icon: AlertTriangle, label: "Cần kiểm tra" },
  unknown: { icon: CircleHelp, label: "Chưa có mẫu đo" },
};

export default function StatusBadge({ status, label }: { status: StatusTone | string; label?: string }) {
  const normalized = status in config ? status as StatusTone : "unknown";
  const item = config[normalized];
  const Icon = item.icon;
  return (
    <span className={`status-badge ${normalized}`} role="status">
      <Icon size={14} aria-hidden="true" />
      {label || item.label}
    </span>
  );
}
