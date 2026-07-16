import { LoaderCircle } from "lucide-react";

export default function TaskProgress({
  label,
  elapsedSeconds,
  progress,
}: {
  label: string;
  elapsedSeconds: number;
  progress?: number;
}) {
  const bounded = progress == null ? undefined : Math.max(0, Math.min(progress, 100));
  return (
    <div className="task-progress" role="status">
      <div>
        <LoaderCircle className="spin" size={16} aria-hidden="true" />
        <strong>{label}</strong>
        <span>{elapsedSeconds}s</span>
      </div>
      <div className={bounded == null ? "progress-track indeterminate" : "progress-track"}>
        <i style={bounded == null ? undefined : { width: `${bounded}%` }} />
      </div>
    </div>
  );
}
