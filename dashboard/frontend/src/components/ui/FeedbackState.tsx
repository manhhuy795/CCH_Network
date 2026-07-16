import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";

type Kind = "empty" | "error" | "loading";
const icons = { empty: Inbox, error: AlertCircle, loading: LoaderCircle };

export default function FeedbackState({
  kind,
  title,
  message,
  action,
}: {
  kind: Kind;
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  const Icon = icons[kind];
  return (
    <div className={`feedback-state ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon size={22} aria-hidden="true" />
      <strong>{title}</strong>
      <p>{message}</p>
      {action}
    </div>
  );
}
