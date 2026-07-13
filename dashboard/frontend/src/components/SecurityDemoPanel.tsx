import { Ban, LockKeyhole, ShieldCheck, UserCog } from "lucide-react";

type Scenario = {
  id: string;
  title: string;
  description: string;
  source: string;
  destination: string;
  action: "ping" | "simulate" | "block" | "unblock";
  icon: "lock" | "ban" | "it" | "shield";
};

const scenarios: Scenario[] = [
  {
    id: "project-isolation",
    title: "Cách ly Project",
    description: "Dự án A ping Dự án B phải bị chặn tại HQ Core.",
    source: "h20_01",
    destination: "h30_01",
    action: "ping",
    icon: "lock",
  },
  {
    id: "social-block",
    title: "Chặn Social Media",
    description: "User thường truy cập Social Media phải bị chặn tại firewall site.",
    source: "h20_01",
    destination: "hsocial",
    action: "ping",
    icon: "ban",
  },
  {
    id: "it-remote",
    title: "IT Remote Support",
    description: "Phòng IT remote tới user dự án được cho phép.",
    source: "h70_01",
    destination: "h20_01",
    action: "ping",
    icon: "it",
  },
  {
    id: "emergency-block",
    title: "Chặn khẩn cấp",
    description: "IT cài drop flow tạm thời cho một cặp endpoint.",
    source: "h70_01",
    destination: "h20_01",
    action: "block",
    icon: "shield",
  },
  {
    id: "recover-block",
    title: "Gỡ chặn",
    description: "Xóa drop flow tạm thời để khôi phục hỗ trợ.",
    source: "h70_01",
    destination: "h20_01",
    action: "unblock",
    icon: "shield",
  },
];

const icons = {
  lock: LockKeyhole,
  ban: Ban,
  it: UserCog,
  shield: ShieldCheck,
};

export default function SecurityDemoPanel({ busy, onRun }: {
  busy: boolean;
  onRun: (scenario: Scenario) => void;
}) {
  return (
    <section>
      <div className="section-title"><h2>Demo bảo mật trực quan</h2><span>RBAC · Segmentation · OpenFlow drop</span></div>
      <div className="security-demo-list">
        {scenarios.map((scenario) => {
          const Icon = icons[scenario.icon];
          return (
            <button key={scenario.id} disabled={busy} onClick={() => onRun(scenario)}>
              <Icon size={16} />
              <span><strong>{scenario.title}</strong><small>{scenario.description}</small></span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
