import { useState } from "react";
import { useCameras } from "../hooks/useCameras";
import { useStartTracking, useStopTracking, useTrackingStatus } from "../hooks/useTracking";
import { LineEditor } from "../components/LineEditor";
import { ModuleSelector } from "../components/ModuleSelector";
import { ZoneEditor } from "../components/ZoneEditor";
import { Button, Card, EmptyState, ErrorNotice, StatusBadge } from "../components/ui";
import { READ_KIND_LABELS, READING_MODULES } from "../modules";
import type { AIModule, Camera, LineCount, Read, TrackingStatusValue } from "../api/types";

const STATUS_TONE: Record<TrackingStatusValue, "success" | "warning" | "danger" | "neutral"> = {
  running: "success",
  reconnecting: "warning",
  starting: "neutral",
  stopped: "neutral",
  error: "danger",
};

const RUNNING_STATUSES: TrackingStatusValue[] = ["starting", "running", "reconnecting"];

/** People counts read exactly as they always did; vehicle counts are added only when the
 * Vehicles module is on (and stand alone when People is off). */
function lineCountText(lc: LineCount, modules: AIModule[]): string {
  const parts: string[] = [];
  if (modules.includes("people")) parts.push(`${lc.in_count} in / ${lc.out_count} out`);
  if (modules.includes("vehicles")) parts.push(`vehicles ${lc.vehicle_in_count} in / ${lc.vehicle_out_count} out`);
  return parts.length > 0 ? `${lc.name}: ${parts.join(" | ")}` : lc.name;
}

function readText(read: Read): string {
  // OCR's `detail` is its confidence (0-1); for QR/barcode it is the symbology name.
  const detail = read.kind === "ocr" ? `${Math.round(Number(read.detail) * 100)}% confident` : read.detail;
  return `${READ_KIND_LABELS[read.kind]}: ${read.value} (${detail}) · seen ${read.sightings}×`;
}

const MAX_READS_SHOWN = 10;

function AIModuleRow({ camera }: { camera: Camera }) {
  const { data: status } = useTrackingStatus(camera.id);
  const startTracking = useStartTracking();
  const stopTracking = useStopTracking();
  const [showLines, setShowLines] = useState(false);
  const [showZones, setShowZones] = useState(false);

  const isRunning = status ? RUNNING_STATUSES.includes(status.status) : false;
  const busy = startTracking.isPending || stopTracking.isPending;

  const modules = camera.enabled_modules;
  const noModules = modules.length === 0;
  const readingModules = modules.filter((m) => READING_MODULES.includes(m));

  const tracked: string[] = [];
  if (status && modules.includes("people")) tracked.push(`${status.active_track_ids.length} person(s) tracked`);
  if (status && modules.includes("vehicles")) tracked.push(`${status.active_vehicle_track_ids.length} vehicle(s) tracked`);

  return (
    <li className="camera-row">
      <div className="camera-row__header">
        <div>
          <strong>{camera.name}</strong>{" "}
          {status && <StatusBadge label={status.status} tone={STATUS_TONE[status.status]} />}
          {status && status.status === "running" && tracked.length > 0 && (
            <span className="camera-row__details"> · {tracked.join(", ")}</span>
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
            <Button variant="primary" onClick={() => startTracking.mutate(camera.id)} disabled={busy || noModules}>
              {startTracking.isPending ? "Starting..." : "Start tracking"}
            </Button>
          )}
        </div>
      </div>

      <ModuleSelector camera={camera} isRunning={isRunning} />
      {noModules && !isRunning && (
        <p className="camera-row__details">Tick at least one AI module to start tracking this camera.</p>
      )}

      {status && status.line_counts.length > 0 && (
        <ul className="camera-row__line-counts">
          {status.line_counts.map((lc) => (
            <li key={lc.line_id}>{lineCountText(lc, modules)}</li>
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

      {status && status.status === "running" && readingModules.length > 0 && status.reads.length === 0 && (
        <p className="camera-row__details">Watching for {readingModules.map((m) => READ_KIND_LABELS[m]).join(", ")}; nothing read yet.</p>
      )}
      {status && status.reads.length > 0 && (
        <div>
          <strong>Recent reads</strong>
          <ul className="camera-row__reads">
            {status.reads.slice(0, MAX_READS_SHOWN).map((read) => (
              <li key={`${read.kind}:${read.value}`}>{readText(read)}</li>
            ))}
          </ul>
        </div>
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
        Choose which modules each camera runs: people and vehicle detection + tracking (with entry/exit line
        counting), custom zones, a heatmap you can switch on in Live View, and reading of text, QR codes and barcodes.
        Changes to a camera&apos;s modules apply the next time its tracking starts.
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
