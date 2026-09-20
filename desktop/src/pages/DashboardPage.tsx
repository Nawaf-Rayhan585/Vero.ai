import { Link } from "react-router-dom";
import { useHealth, useHealthDb } from "../hooks/useHealth";
import { useJobs } from "../hooks/useJobs";
import { useSettings } from "../settings/SettingsContext";
import { Button, Card, EmptyState, StatusBadge } from "../components/ui";
import type { Job, JobStatus } from "../api/types";

const STATUS_ORDER: JobStatus[] = ["pending", "running", "completed", "failed"];

function countByStatus(jobs: Job[]): Record<JobStatus, number> {
  const counts: Record<JobStatus, number> = { pending: 0, running: 0, completed: 0, failed: 0 };
  for (const job of jobs) counts[job.status] += 1;
  return counts;
}

export function DashboardPage() {
  const settings = useSettings();
  const health = useHealth();
  const healthDb = useHealthDb();
  const jobsQuery = useJobs();

  // React Query keeps the last successful `data` around even after a later background
  // refetch fails, so `data` alone can't tell "online" from "was online, now erroring".
  const backendOnline = health.data?.status === "ok" && !health.isError;
  const dbOnline = healthDb.data?.status === "ok" && !healthDb.isError;

  if (!backendOnline) {
    return (
      <Card title="Backend offline">
        <p>Vero.ai can't reach the backend at:</p>
        <p>
          <code>{settings.apiBaseUrl}</code>
        </p>
        <p>Make sure the backend is running, or change the address in Settings.</p>
        <Link to="/settings">Go to Settings</Link>
      </Card>
    );
  }

  const jobs = jobsQuery.data ?? [];
  const counts = countByStatus(jobs);
  const recentJobs = [...jobs].reverse().slice(0, 10);

  return (
    <>
      <div className="dashboard-status-row">
        <Card title="Backend">
          <StatusBadge label="Online" tone="success" />
        </Card>
        <Card title="Database">
          <StatusBadge label={dbOnline ? "Online" : "Unavailable"} tone={dbOnline ? "success" : "danger"} />
        </Card>
        {STATUS_ORDER.map((status) => (
          <Card key={status} title={status}>
            <span className="dashboard-count">{counts[status]}</span>
          </Card>
        ))}
      </div>

      <Card title="Recent detection jobs">
        <div className="row">
          <Button onClick={() => jobsQuery.refetch()} disabled={jobsQuery.isFetching}>
            {jobsQuery.isFetching ? "Refreshing..." : "Refresh"}
          </Button>
          <Link to="/detect">
            <Button variant="primary">New detection</Button>
          </Link>
        </div>

        {recentJobs.length === 0 ? (
          <EmptyState title="No detection jobs yet">
            <Link to="/detect">Run your first detection</Link>
          </EmptyState>
        ) : (
          <ul className="dashboard-job-list">
            {recentJobs.map((job) => (
              <li key={job.id}>
                <Link to={`/detect?job=${job.id}`}>{job.video_source}</Link>
                <StatusBadge label={job.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
