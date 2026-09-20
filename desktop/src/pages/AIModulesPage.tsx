import { useCameras } from "../hooks/useCameras";
import { useStartTracking, useStopTracking, useTrackingStatus } from "../hooks/useTracking";
import { Button, Card, EmptyState, ErrorNotice, StatusBadge } from "../components/ui";
import type { Camera, TrackingStatusValue } from "../api/types";

const STATUS_TONE: Record<TrackingStatusValue, "success" | "warning" | "danger" | "neutral"> = {
  running: "success",
  reconnecting: "warning",
  starting: "neutral",
  stopped: "neutral",
  error: "danger",
};

const RUNNING_STATUSES: TrackingStatusValue[] = ["starting", "running", "reconnecting"];

function AIModuleRow({ camera }: { camera: Camera }) {
  const { data: status } = useTrackingStatus(camera.id);
  const startTracking = useStartTracking();
  const stopTracking = useStopTracking();

  const isRunning = status ? RUNNING_STATUSES.includes(status.status) : false;
  const busy = startTracking.isPending || stopTracking.isPending;

  return (
    <li className="camera-row">
      <div className="camera-row__header">
        <div>
          <strong>{camera.name}</strong>{" "}
          {status && <StatusBadge label={status.status} tone={STATUS_TONE[status.status]} />}
          {status && status.status === "running" && (
            <span className="camera-row__details"> · {status.active_track_ids.length} person(s) tracked</span>
          )}
        </div>
        <div className="row">
          {isRunning ? (
            <Button onClick={() => stopTracking.mutate(camera.id)} disabled={busy}>
              {stopTracking.isPending ? "Stopping..." : "Stop tracking"}
            </Button>
          ) : (
            <Button variant="primary" onClick={() => startTracking.mutate(camera.id)} disabled={busy}>
              {startTracking.isPending ? "Starting..." : "Start tracking"}
            </Button>
          )}
        </div>
      </div>

      {status?.status === "error" && status.error && <ErrorNotice message={status.error} />}
      {startTracking.isError && <ErrorNotice message={startTracking.error.message} />}
      {stopTracking.isError && <ErrorNotice message={stopTracking.error.message} />}
    </li>
  );
}

export function AIModulesPage() {
  const { data: cameras, isLoading, isError, error } = useCameras();

  return (
    <Card title="AI Modules">
      <p style={{ color: "var(--color-text-muted)" }}>
        Person detection + tracking. Other modules (counting, zones, heatmaps, vehicles, OCR, QR, barcode) arrive in
        later phases.
      </p>

      {isLoading && null}
      {isError && <ErrorNotice message={error.message} />}

      {cameras && cameras.length === 0 && <EmptyState title="No cameras yet">Add a camera on the Cameras page first.</EmptyState>}

      {cameras && cameras.length > 0 && (
        <ul className="camera-list">
          {cameras.map((camera) => (
            <AIModuleRow key={camera.id} camera={camera} />
          ))}
        </ul>
      )}
    </Card>
  );
}
