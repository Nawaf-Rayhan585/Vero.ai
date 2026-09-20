import { Link } from "react-router-dom";
import { Card } from "../components/ui";

export function NotFoundPage() {
  return (
    <Card title="Not found">
      <p>That page doesn't exist.</p>
      <Link to="/">Go to Dashboard</Link>
    </Card>
  );
}
