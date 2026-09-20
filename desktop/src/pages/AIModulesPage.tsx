import { useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useStartTracking, useStopTracking, useTrackingStatus } from "../hooks/useTracking";
import { LineEditor } from "../components/LineEditor";
import { ZoneEditor } from "../components/ZoneEditor";
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
  const [showLines, setShowLines] = useState(false);
  const [showZones, setShowZones] = useState(false);

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
          <Button onClick={() => setShowLines((v) => !v)}>{showLines ? "Hide lines" : "Lines"}</Button>
          <Button onClick={() => setShowZones((v) => !v)}>{showZones ? "Hide zones" : "Zones"}</Button>
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

      {status && status.line_counts.length > 0 && (
        <ul className="camera-row__line-counts">
          {status.line_counts.map((lc) => (
            <li key={lc.line_id}>
              {lc.name}: {lc.in_count} in / {lc.out_count} out
            </li>
          ))}
        </ul>
      )}

      {status && status.zone_counts.length > 0 && (
        <ul className="camera-row__line-counts">
          {status.zone_counts.map((zc) => (
            <li key={zc.zone_id}>
              {zc.name}: {zc.count} inside
            </li>
          ))}
        </ul>
      )}

      {status?.status === "error" && status.error && <ErrorNotice message={status.error} />}
      {startTracking.isError && <ErrorNotice message={startTracking.error.message} />}
      {stopTracking.isError && <ErrorNotice message={stopTracking.error.message} />}

      {showLines && <LineEditor cameraId={camera.id} />}
      {showZones && <ZoneEditor cameraId={camera.id} />}
    </li>
  );
}

export function AIModulesPage() {
  const { data: cameras, isLoading, isError, error } = useCameras();

  return (
    <Card title="AI Modules">
      <p style={{ color: "var(--color-text-muted)" }}>
        Person detection + tracking, with entry/exit line counting, custom zones (a live count of who is inside), and
        a heatmap you can switch on in Live View. Other modules (vehicles, OCR, QR, barcode) arrive in later phases.
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
