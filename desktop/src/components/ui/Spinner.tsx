import "./Spinner.css";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <span className="vero-spinner" role="status" aria-label={label} />;
}
