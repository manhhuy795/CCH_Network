import { CheckCircle2, Cpu, Layers, Power, Search, ShieldCheck, Zap } from "lucide-react";
import { useMemo, useState } from "react";
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

function policyCategory(key: string): { label: string; tone: "project" | "voice" | "wan" | "security" } {
  if (key.includes("isolate") || key.includes("project")) return { label: "Default-deny & Phân đoạn", tone: "project" };
  if (key.includes("voice") || key.includes("softphone") || key.includes("call")) return { label: "Thoại & flow priority", tone: "voice" };
  if (key.includes("vpn") || key.includes("ipsec") || key.includes("intersite")) return { label: "WAN & Intersite", tone: "wan" };
  return { label: "Internet & Bảo mật Biên", tone: "security" };
}

export default function PolicyPanel({ policies, onToggle, busy = false }: Props) {
  const [pending, setPending] = useState<PolicyInventoryItem>();
  const [applyingKey, setApplyingKey] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const inventory = useMemo(() => policies.inventory || [], [policies.inventory]);

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

  const filteredInventory = useMemo(() => {
    return inventory.filter((item) => {
      if (categoryFilter !== "all") {
        const cat = policyCategory(item.key).tone;
        if (cat !== categoryFilter) return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const text = `${item.name} ${item.key} ${item.description} ${item.source} ${item.destination} ${item.enforcement_point}`.toLowerCase();
        if (!text.includes(q)) return false;
      }
      return true;
    });
  }, [inventory, categoryFilter, searchQuery]);

  const activeCount = inventory.filter((i) => i.enabled).length;
  const appliedCount = inventory.filter((i) => i.lifecycle_status === "Applied").length;
  const openflowCount = inventory.filter((i) => i.enforcement_engine === "openflow").length;
  const nftablesCount = inventory.filter((i) => i.enforcement_engine === "nftables").length;
  const pendingCount = inventory.length - appliedCount;

  return (
    <section className="policy-section-card">
      <div className="section-title">
        <div>
          <h2>Trung tâm chính sách mạng</h2>
          <span>Quản lý chính sách bảo mật, phân đoạn L2/L3 và flow priority cho Voice</span>
        </div>
        <StatusBadge
          status={inventory.some((item) => item.lifecycle_status === "Failed") ? "offline" : inventory.some((item) => item.lifecycle_status !== "Applied") ? "degraded" : "online"}
          label={`${appliedCount}/${inventory.length} Đã áp dụng`}
        />
      </div>

      <div className="policy-hero-stats">
        <div className="policy-stat-card">
          <div className="stat-icon-badge blue">
            <ShieldCheck size={18} />
          </div>
          <div>
            <div className="stat-number">{activeCount} / {inventory.length}</div>
            <div className="stat-title">Chính sách Hoạt động</div>
            <small className="stat-desc">{appliedCount} policy đã được runtime xác nhận</small>
          </div>
        </div>

        <div className="policy-stat-card">
          <div className="stat-icon-badge purple">
            <Cpu size={18} />
          </div>
          <div>
            <div className="stat-number">{openflowCount}</div>
            <div className="stat-title">OpenFlow 1.3</div>
            <small className="stat-desc">Policy thực thi trên OVS do OS-Ken quản lý</small>
          </div>
        </div>

        <div className="policy-stat-card">
          <div className="stat-icon-badge green">
            <Layers size={18} />
          </div>
          <div>
            <div className="stat-number">{nftablesCount}</div>
            <div className="stat-title">Stateful nftables</div>
            <small className="stat-desc">Policy Internet và Partner tại firewall hai site</small>
          </div>
        </div>

        <div className="policy-stat-card">
          <div className="stat-icon-badge amber">
            <Zap size={18} />
          </div>
          <div>
            <div className="stat-number">{pendingCount}</div>
            <div className="stat-title">Chưa đồng bộ</div>
            <small className="stat-desc">Draft, Applying, Failed hoặc Out of sync</small>
          </div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="policy-filter-bar">
        <div className="category-tabs" role="tablist" aria-label="Lọc nhóm chính sách">
          <button
            type="button"
            className={categoryFilter === "all" ? "active" : ""}
            onClick={() => setCategoryFilter("all")}
          >
            Tất cả ({inventory.length})
          </button>
          <button
            type="button"
            className={categoryFilter === "project" ? "active" : ""}
            onClick={() => setCategoryFilter("project")}
          >
            Default-deny & Phân đoạn
          </button>
          <button
            type="button"
            className={categoryFilter === "voice" ? "active" : ""}
            onClick={() => setCategoryFilter("voice")}
          >
            Thoại & flow priority
          </button>
          <button
            type="button"
            className={categoryFilter === "wan" ? "active" : ""}
            onClick={() => setCategoryFilter("wan")}
          >
            WAN & Intersite
          </button>
          <button
            type="button"
            className={categoryFilter === "security" ? "active" : ""}
            onClick={() => setCategoryFilter("security")}
          >
            Internet & Bảo mật Biên
          </button>
        </div>

        <div className="policy-search-input">
          <Search size={14} />
          <input
            type="text"
            placeholder="Tìm theo tên, key, subnet, thiết bị..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Policies Inventory List */}
      <div className="policy-inventory" aria-live="polite">
        {filteredInventory.map((policy) => {
          const lifecycle = applyingKey === policy.key ? "Applying" : policy.lifecycle_status;
          const category = policyCategory(policy.key);
          return (
            <article className={`policy-row ${category.tone}`} key={policy.key}>
              <div className="policy-heading">
                <div className="policy-title-block">
                  <div className="policy-title-row">
                    <strong>{policy.name}</strong>
                    <span className={`category-pill ${category.tone}`}>{category.label}</span>
                    <span className={`engine-pill ${policy.enforcement_engine === "nftables" ? "nftables" : "openflow"}`}>
                      {policy.enforcement_engine === "nftables" ? "nftables (Kernel)" : "OpenFlow 1.3 (OVS)"}
                    </span>
                  </div>
                  <code>{policy.key}</code>
                </div>
                <div className="policy-statuses">
                  <StatusBadge status={policy.enabled ? "online" : policy.enabled === false ? "offline" : "unknown"} label={policy.configuration_status} />
                  <StatusBadge status={lifecycleTone(lifecycle)} label={lifecycle} />
                </div>
              </div>

              <p className="policy-description-text">{policy.description}</p>

              <dl className="policy-facts">
                <div>
                  <dt>Nguồn</dt>
                  <dd className="code-font">{policy.source}</dd>
                </div>
                <div>
                  <dt>Đích</dt>
                  <dd className="code-font">{policy.destination}</dd>
                </div>
                <div>
                  <dt>Action</dt>
                  <dd>
                    <span className={`pill ${policy.action === "ALLOW" ? "allow" : "deny"}`}>
                      {policy.action === "ALLOW" ? "✓ ALLOW" : "✕ DENY"}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>Enforcement</dt>
                  <dd><strong>{policy.enforcement_point}</strong></dd>
                </div>
                <div>
                  <dt>Priority</dt>
                  <dd className="highlight-metric">{policy.priority}</dd>
                </div>
                <div>
                  <dt>Cookie</dt>
                  <dd><code>{policy.cookie}</code></dd>
                </div>
                <div>
                  <dt>Engine</dt>
                  <dd>{policy.enforcement_engine === "nftables" ? "nftables" : "OpenFlow"}</dd>
                </div>
                <div>
                  <dt aria-label="controller acknowledgement">Runtime ACK</dt>
                  <dd className="ack-status">
                    {policy.runtime_acknowledged ?? policy.controller_acknowledged ? (
                      <span className="ack-ok"><CheckCircle2 size={13} /> Đã xác nhận</span>
                    ) : (
                      <span className="ack-pending">Chưa xác nhận</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Cập nhật</dt>
                  <dd>{formatTime(policy.updated_at)}</dd>
                </div>
              </dl>

              {onToggle && policy.enabled !== null && (
                <div className="policy-actions">
                  <button
                    className={policy.enabled ? "danger" : "primary"}
                    disabled={busy || Boolean(applyingKey)}
                    onClick={() => setPending(policy)}
                  >
                    <Power size={15} />
                    {policy.enabled ? "Tắt policy" : "Bật policy"}
                  </button>
                </div>
              )}
            </article>
          );
        })}
        {!filteredInventory.length && (
          <p className="empty-inline">
            {inventory.length ? "Không có chính sách nào khớp với bộ lọc." : "Backend chưa trả policy inventory."}
          </p>
        )}
      </div>

      <div className="explanation">
        <h3>Ranh giới thực thi</h3>
        <p>Segmentation SDN thực thi tại các switch core và access theo policy. Internet Edge Boundary thực thi policy Internet bằng stateful nftables tại firewall hai site; firewall không phải OpenFlow device.</p>
        <p>MPLS L2VPN Primary/Backup và IPsec L3 là contract truyền dẫn của topology, không được trình bày như OpenFlow policy có thể bật/tắt tại đây.</p>
        <p>Ghi policy.yml chỉ là thay đổi cấu hình. Trạng thái Applied chỉ xuất hiện sau khi OS-Ken và nftables liên quan reload, xác nhận thành công.</p>
      </div>

      <ConfirmDialog
        open={Boolean(pending)}
        title={pending?.enabled ? "Tắt chính sách đang áp dụng?" : "Bật chính sách này?"}
        message={
          pending
            ? `Tác động: ${pending.action} ${pending.source} → ${pending.destination} tại ${pending.enforcement_point}. ${pending.enforcement_engine === "nftables" ? "Hai firewall sẽ reload table inet cch_filter" : `Controller sẽ reconcile flow cookie ${pending.cookie}`}; lưu lượng đang chạy có thể thay đổi ngay.`
            : ""
        }
        confirmLabel={pending?.enabled ? "Tắt policy" : "Bật policy"}
        danger={Boolean(pending?.enabled)}
        onClose={() => setPending(undefined)}
        onConfirm={() => void confirmToggle()}
      />
    </section>
  );
}
