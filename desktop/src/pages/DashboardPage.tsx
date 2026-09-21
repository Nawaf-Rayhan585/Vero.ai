import { Link } from "react-router-dom";
import { useMemo } from "react";
import { useAnalyticsSummary } from "../hooks/useAnalytics";
import { useHealth, useHealthDb } from "../hooks/useHealth";
import { useJobs } from "../hooks/useJobs";
import { useSettings } from "../settings/SettingsContext";
import { StatTile, StatTiles } from "../components/StatTile";
import { Button, Card, EmptyState, StatusBadge } from "../components/ui";
import { formatDuration, formatNumber } from "../lib/format";
import { todaySince } from "../lib/ranges";
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
  const todayQuery = useMemo(() => ({ since: todaySince() }), []);
  const today = useAnalyticsSummary(todayQuery);

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

      {/* If the summary can't be loaded the card is simply left out: the dashboard's job is to
          show the backend is up, and a missing tile shouldn't look like an error of its own. */}
      {today.data && !today.isError && (
        <Card title="Today">
          <StatTiles>
            <StatTile label="People in" value={formatNumber(today.data.people_in)} />
            <StatTile label="People out" value={formatNumber(today.data.people_out)} />
            <StatTile label="Vehicles in" value={formatNumber(today.data.vehicle_in)} />
            <StatTile label="Vehicles out" value={formatNumber(today.data.vehicle_out)} />
            <StatTile
              label="Reads"
              value={formatNumber(today.data.reads.qr + today.data.reads.barcode + today.data.reads.ocr)}
              hint="QR, barcode and text"
            />
            <StatTile label="Tracked" value={formatDuration(today.data.tracked_seconds)} hint="camera time today" />
          </StatTiles>
          <Link to="/analytics">See analytics</Link>
        </Card>
      )}

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
