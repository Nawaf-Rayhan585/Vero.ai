import "./StatusBadge.css";

type Tone = "success" | "warning" | "danger" | "neutral";

const TONE_BY_JOB_STATUS: Record<string, Tone> = {
  completed: "success",
  running: "warning",
  pending: "neutral",
  failed: "danger",
};

export function StatusBadge({ label, tone }: { label: string; tone?: Tone }) {
  const resolvedTone = tone ?? TONE_BY_JOB_STATUS[label] ?? "neutral";
  return <span className={`vero-status-badge vero-status-badge--${resolvedTone}`}>{label}</span>;
}
