import { Card } from "../components/ui";

export function PlaceholderPage({ title, description, phase }: { title: string; description: string; phase: string }) {
  return (
    <Card title={title}>
      <p>{description}</p>
      <p style={{ color: "var(--color-text-muted)" }}>Planned for {phase}. Not built yet.</p>
    </Card>
  );
}
