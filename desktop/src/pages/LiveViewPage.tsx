import { useEffect, useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useCameraSnapshot } from "../hooks/useCameraSnapshot";
import { useTrackingFrame } from "../hooks/useTrackingFrame";
import { useTrackingStatus } from "../hooks/useTracking";
import { Card, EmptyState, ErrorNotice, StatusBadge } from "../components/ui";
import type { TrackingStatusValue } from "../api/types";

const ACTIVE_TRACKING_STATUSES: TrackingStatusValue[] = ["starting", "running", "reconnecting"];

const STATUS_TONE: Record<TrackingStatusValue, "success" | "warning" | "danger" | "neutral"> = {
  running: "success",
  reconnecting: "warning",
  starting: "neutral",
  stopped: "neutral",
  error: "danger",
};

export function LiveViewPage() {
  const { data: cameras, isLoading } = useCameras();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!cameras || cameras.length === 0) return;
    if (!cameras.some((c) => c.id === selectedId)) {
      setSelectedId(cameras[0].id);
    }
  }, [cameras, selectedId]);

  // Whichever feed applies is decided by tracking status, not a manual toggle — Live
  // View should just reflect whatever's actually running for this camera.
  const trackingStatus = useTrackingStatus(selectedId);
  const statusKnown = trackingStatus.data !== undefined;
  const isTrackingActive = statusKnown && ACTIVE_TRACKING_STATUSES.includes(trackingStatus.data!.status);

  // Neither feed is enabled until we know which one applies — otherwise the snapshot
  // fetch would fire on every camera selection before the tracking-status check
  // resolves, even when tracking turns out to already be running.
  const snapshot = useCameraSnapshot(statusKnown && !isTrackingActive ? selectedId : null);
  const trackingFrame = useTrackingFrame(statusKnown && isTrackingActive ? selectedId : null);
  const activeFeed = isTrackingActive ? trackingFrame : snapshot;

  const selected = cameras?.find((c) => c.id === selectedId) ?? null;
  // See DashboardPage.tsx: react-query keeps the last successful `data` around during a
  // failed refetch, so a stale frame from before the camera went offline would otherwise
  // keep showing instead of the error.
  const showImage = activeFeed.data && !activeFeed.isError;

  if (isLoading) return null;

  if (!cameras || cameras.length === 0) {
    return (
      <Card title="Live View">
        <EmptyState title="No cameras yet">Add a camera on the Cameras page first.</EmptyState>
      </Card>
    );
  }

  return (
    <Card title="Live View">
      <div className="settings-row">
        <label htmlFor="live-view-camera-select">Camera</label>
        <select
          id="live-view-camera-select"
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.currentTarget.value)}
        >
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {isTrackingActive && trackingStatus.data && (
        <div className="row">
          <span>AI tracking:</span>
          <StatusBadge label={trackingStatus.data.status} tone={STATUS_TONE[trackingStatus.data.status]} />
        </div>
      )}

      {selected && showImage && (
        <img className="live-view-preview" src={activeFeed.data} alt={`Live snapshot from ${selected.name}`} />
      )}
      {selected && activeFeed.isError && (
        <ErrorNotice
          message={`Could not get a snapshot from "${selected.name}". It may be offline — check Cameras.`}
        />
      )}
    </Card>
  );
}
