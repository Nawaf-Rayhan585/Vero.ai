import { useState, type MouseEvent } from "react";
import { useCameraSnapshot } from "../hooks/useCameraSnapshot";
import { useCreateZone, useDeleteZone, useZones } from "../hooks/useZones";
import type { ZonePoint } from "../api/types";
import { Button, ErrorNotice, Spinner } from "./ui";

const MIN_POINTS = 3;

function toSvgPoints(points: ZonePoint[]): string {
  return points.map((p) => `${p.x * 100},${p.y * 100}`).join(" ");
}

export function ZoneEditor({ cameraId }: { cameraId: string }) {
  const snapshot = useCameraSnapshot(cameraId);
  const { data: zones } = useZones(cameraId);
  const createZone = useCreateZone(cameraId);
  const deleteZone = useDeleteZone(cameraId);

  const [draftPoints, setDraftPoints] = useState<ZonePoint[]>([]);
  // Once finished, the outline is closed and no further points can be added.
  const [finished, setFinished] = useState(false);
  const [name, setName] = useState("");

  function reset() {
    setDraftPoints([]);
    setFinished(false);
    setName("");
  }

  function handleImageClick(e: MouseEvent<HTMLImageElement>) {
    if (finished) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // Normalized 0-1 against the *rendered* size, not the image's natural resolution —
    // resolution-independent, exactly like LineEditor.
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDraftPoints((prev) => [...prev, { x, y }]);
  }

  function handleSave() {
    if (!finished || draftPoints.length < MIN_POINTS || !name.trim()) return;
    createZone.mutate({ name: name.trim(), points: draftPoints }, { onSuccess: reset });
  }

  const canFinish = !finished && draftPoints.length >= MIN_POINTS;

  return (
    <div className="line-editor">
      {snapshot.isLoading && <Spinner label="Loading camera frame" />}
      {snapshot.isError && <ErrorNotice message="Could not load a frame from this camera to draw on. Check Cameras." />}

      {snapshot.data && (
        <div className="line-editor__canvas-wrap">
          <img
            src={snapshot.data}
            alt="Camera frame for zone placement"
            className="line-editor__image"
            onClick={handleImageClick}
          />
          <svg className="line-editor__overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
            {zones?.map((zone) => (
              <polygon key={zone.id} points={toSvgPoints(zone.points)} className="line-editor__existing-zone" />
            ))}
            {draftPoints.length >= 2 &&
              (finished ? (
                <polygon points={toSvgPoints(draftPoints)} className="line-editor__draft-zone line-editor__draft-zone--closed" />
              ) : (
                <polyline points={toSvgPoints(draftPoints)} className="line-editor__draft-zone" />
              ))}
            {draftPoints.map((p, i) => (
              <circle key={i} cx={p.x * 100} cy={p.y * 100} r={1.2} className="line-editor__draft-point" />
            ))}
          </svg>
        </div>
      )}

      {draftPoints.length === 0 && (
        <p className="camera-row__details">Click 3 or more points on the image to outline a zone.</p>
      )}
      {draftPoints.length > 0 && draftPoints.length < MIN_POINTS && (
        <p className="camera-row__details">
          {draftPoints.length} point(s) placed — keep clicking, a zone needs at least {MIN_POINTS}.
        </p>
      )}
      {canFinish && (
        <p className="camera-row__details">
          {draftPoints.length} points placed — click more to refine the outline, or finish the zone.
        </p>
      )}

      {draftPoints.length > 0 && !finished && (
        <div className="row">
          <Button onClick={() => setDraftPoints((prev) => prev.slice(0, -1))}>Undo last point</Button>
          <Button variant="primary" onClick={() => setFinished(true)} disabled={!canFinish}>
            Finish zone
          </Button>
          <Button onClick={reset}>Cancel</Button>
        </div>
      )}

      {finished && (
        <div className="row">
          <label htmlFor={`zone-name-${cameraId}`}>Name</label>
          <input
            id={`zone-name-${cameraId}`}
            type="text"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder="e.g. Checkout area"
          />
          <Button variant="primary" onClick={handleSave} disabled={!name.trim() || createZone.isPending}>
            {createZone.isPending ? "Saving..." : "Save zone"}
          </Button>
          <Button onClick={reset}>Cancel</Button>
        </div>
      )}
      {createZone.isError && <ErrorNotice message={createZone.error.message} />}

      {zones && zones.length > 0 && (
        <ul className="line-editor__list">
          {zones.map((zone) => (
            <li key={zone.id}>
              <span>{zone.name}</span>
              <Button onClick={() => deleteZone.mutate(zone.id)} disabled={deleteZone.isPending}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
