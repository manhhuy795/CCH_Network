import { Power } from "lucide-react";
import { useState } from "react";
import type { PolicyInventoryItem, PolicyPayload } from "../api/client";
import ConfirmDialog from "./ui/ConfirmDialog";
import StatusBadge from "./ui/StatusBadge";

type Props = {
  policies: PolicyPayload;
  onToggle?: (key: string, enabled: boolean) => Promise<void> | void;
  busy?: boolean;
};

function lifecycleTone(status: PolicyInventoryItem["lifecycle_status"]) {
  if (status === "Applied") return "online";
  if (status === "Failed") return "offline";
  if (status === "Applying" || status === "Out of sync") return "degraded";
  return "unknown";
}

function formatTime(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value || "Chưa có" : parsed.toLocaleString("vi-VN");
}

export default function PolicyPanel({ policies, onToggle, busy = false }: Props) {
  const [pending, setPending] = useState<PolicyInventoryItem>();
  const [applyingKey, setApplyingKey] = useState("");
  const inventory = policies.inventory || [];

  const confirmToggle = async () => {
    if (!pending || !onToggle) return;
    setApplyingKey(pending.key);
    try {
      await onToggle(pending.key, !pending.enabled);
    } finally {
      setApplyingKey("");
      setPending(undefined);
    }
  };

  return (
    <section>
      <div className="section-title">
        <div><h2>Chính sách SDN Edge</h2><span>Trạng thái áp dụng phải có controller acknowledgement</span></div>
        <StatusBadge status={inventory.some((item) => item.lifecycle_status === "Failed") ? "offline" : inventory.some((item) => item.lifecycle_status !== "Applied") ? "degraded" : "online"} />
      </div>
      <div className="policy-inventory" aria-live="polite">
        {inventory.map((policy) => {
          const lifecycle = applyingKey === policy.key ? "Applying" : policy.lifecycle_status;
          return (
            <article className="policy-row" key={policy.key}>
              <div className="policy-heading">
                <div><strong>{policy.name}</strong><code>{policy.key}</code></div>
                <div className="policy-statuses">
                  <StatusBadge status={policy.enabled ? "online" : policy.enabled === false ? "offline" : "unknown"} label={policy.configuration_status} />
                  <StatusBadge status={lifecycleTone(lifecycle)} label={lifecycle} />
                </div>
              </div>
              <p>{policy.description}</p>
              <dl className="policy-facts">
                <div><dt>Nguồn</dt><dd>{policy.source}</dd></div>
                <div><dt>Đích</dt><dd>{policy.destination}</dd></div>
                <div><dt>Action</dt><dd><span className={`pill ${policy.action === "ALLOW" ? "allow" : "deny"}`}>{policy.action}</span></dd></div>
                <div><dt>Enforcement</dt><dd>{policy.enforcement_point}</dd></div>
                <div><dt>Priority</dt><dd>{policy.priority}</dd></div>
                <div><dt>Cookie</dt><dd><code>{policy.cookie}</code></dd></div>
                <div><dt>Controller ACK</dt><dd>{policy.controller_acknowledged ? "Đã xác nhận" : "Chưa xác nhận"}</dd></div>
                <div><dt>Cập nhật</dt><dd>{formatTime(policy.updated_at)}</dd></div>
              </dl>
              {onToggle && policy.enabled !== null && (
                <div className="policy-actions">
                  <button
                    className={policy.enabled ? "danger" : "primary"}
                    disabled={busy || Boolean(applyingKey)}
                    onClick={() => setPending(policy)}
                  >
                    <Power size={15} />{policy.enabled ? "Tắt policy" : "Bật policy"}
                  </button>
                </div>
              )}
            </article>
          );
        })}
        {!inventory.length && <p className="empty-inline">Backend chưa trả policy inventory.</p>}
      </div>
      <div className="explanation">
        <h3>Ranh giới thực thi</h3>
        <p>Policy HQ thực thi tại core_hq; policy Telesale thực thi tại dist_telesale. CE, Firewall, MPLS và Internet Edge Boundary không được coi là OpenFlow device.</p>
        <p>Ghi policy.yml chỉ là thay đổi cấu hình. Trạng thái Applied chỉ xuất hiện sau khi OS-Ken reload và acknowledgement thành công.</p>
      </div>
      <ConfirmDialog
        open={Boolean(pending)}
        title={pending?.enabled ? "Tắt chính sách đang áp dụng?" : "Bật chính sách này?"}
        message={pending
          ? `Tác động: ${pending.action} ${pending.source} → ${pending.destination} tại ${pending.enforcement_point}. Controller sẽ reconcile flow cookie ${pending.cookie}; lưu lượng đang chạy có thể thay đổi ngay.`
          : ""}
        confirmLabel={pending?.enabled ? "Tắt policy" : "Bật policy"}
        danger={Boolean(pending?.enabled)}
        onClose={() => setPending(undefined)}
        onConfirm={() => void confirmToggle()}
      />
    </section>
  );
}
