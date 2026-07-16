import { CheckCircle2, Info, TriangleAlert, X } from "lucide-react";

export type ToastItem = {
  id: string;
  message: string;
  tone: "success" | "error" | "info";
};

const icons = { success: CheckCircle2, error: TriangleAlert, info: Info };

export default function ToastRegion({ items, onDismiss }: { items: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div className="toast-region" aria-live="polite">
      {items.map((item) => {
        const Icon = icons[item.tone];
        return (
          <div className={`toast ${item.tone}`} key={item.id}>
            <Icon size={17} aria-hidden="true" />
            <span>{item.message}</span>
            <button className="icon-button" title="Đóng thông báo" onClick={() => onDismiss(item.id)}><X size={15} /></button>
          </div>
        );
      })}
    </div>
  );
}
