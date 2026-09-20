import { useState, type MouseEvent } from "react";
import { useCameraSnapshot } from "../hooks/useCameraSnapshot";
import { useCreateLine, useDeleteLine, useLines } from "../hooks/useLines";
import { Button, ErrorNotice, Spinner } from "./ui";

interface DraftPoint {
  x: number;
  y: number;
}

export function LineEditor({ cameraId }: { cameraId: string }) {
  const snapshot = useCameraSnapshot(cameraId);
  const { data: lines } = useLines(cameraId);
  const createLine = useCreateLine(cameraId);
  const deleteLine = useDeleteLine(cameraId);

  const [draftPoints, setDraftPoints] = useState<DraftPoint[]>([]);
  const [name, setName] = useState("");

  function reset() {
    setDraftPoints([]);
    setName("");
  }

  function handleImageClick(e: MouseEvent<HTMLImageElement>) {
    if (draftPoints.length >= 2) return;
    const rect = e.currentTarget.getBoundingClientRect();
    // Normalized 0-1 against the *rendered* size, not the image's natural resolution —
    // resolution-independent, matching how the backend stores and later denormalizes
    // line coordinates against whatever the actual frame size turns out to be.
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setDraftPoints((prev) => [...prev, { x, y }]);
  }

  function handleSave() {
    if (draftPoints.length !== 2 || !name.trim()) return;
    const [p1, p2] = draftPoints;
    createLine.mutate({ name: name.trim(), x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y }, { onSuccess: reset });
  }

  return (
    <div className="line-editor">
      {snapshot.isLoading && <Spinner label="Loading camera frame" />}
      {snapshot.isError && <ErrorNotice message="Could not load a frame from this camera to draw on. Check Cameras." />}

      {snapshot.data && (
        <div className="line-editor__canvas-wrap">
          <img
            src={snapshot.data}
            alt="Camera frame for line placement"
            className="line-editor__image"
            onClick={handleImageClick}
          />
          <svg className="line-editor__overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
            {lines?.map((line) => (
              <line
                key={line.id}
                x1={line.x1 * 100}
                y1={line.y1 * 100}
                x2={line.x2 * 100}
                y2={line.y2 * 100}
                className="line-editor__existing-line"
              />
            ))}
            {draftPoints.length === 2 && (
              <line
                x1={draftPoints[0].x * 100}
                y1={draftPoints[0].y * 100}
                x2={draftPoints[1].x * 100}
                y2={draftPoints[1].y * 100}
                className="line-editor__draft-line"
              />
            )}
            {draftPoints.map((p, i) => (
              <circle key={i} cx={p.x * 100} cy={p.y * 100} r={1.2} className="line-editor__draft-point" />
            ))}
          </svg>
        </div>
      )}

      {draftPoints.length === 0 && <p className="camera-row__details">Click two points on the image to place a line.</p>}
      {draftPoints.length === 1 && <p className="camera-row__details">Click one more point to finish the line.</p>}
      {draftPoints.length === 2 && (
        <div className="row">
          <label htmlFor={`line-name-${cameraId}`}>Name</label>
          <input
            id={`line-name-${cameraId}`}
            type="text"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder="e.g. Front entrance"
          />
          <Button variant="primary" onClick={handleSave} disabled={!name.trim() || createLine.isPending}>
            {createLine.isPending ? "Saving..." : "Save line"}
          </Button>
          <Button onClick={reset}>Cancel</Button>
        </div>
      )}
      {createLine.isError && <ErrorNotice message={createLine.error.message} />}

      {lines && lines.length > 0 && (
        <ul className="line-editor__list">
          {lines.map((line) => (
            <li key={line.id}>
              <span>{line.name}</span>
              <Button onClick={() => deleteLine.mutate(line.id)} disabled={deleteLine.isPending}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
