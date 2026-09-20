import { useState } from "react";
import { useCameras, useCreateCamera, useDeleteCamera, useUpdateCamera } from "../hooks/useCameras";
import { useTestCameraConnection } from "../hooks/useCameraTest";
import { Button, Card, EmptyState, ErrorNotice, Spinner, StatusBadge } from "../components/ui";
import type { Camera, CameraCreateRequest, ConnectionStatus } from "../api/types";

const STATUS_TONE: Record<ConnectionStatus, "success" | "danger" | "neutral"> = {
  online: "success",
  offline: "danger",
  unknown: "neutral",
};

const EMPTY_FORM: CameraCreateRequest = {
  name: "",
  rtsp_url: "",
  username: "",
  password: "",
  location_label: "",
  notes: "",
};

function toUpdatePayload(form: CameraCreateRequest): CameraCreateRequest {
  // "" -> undefined for optional text fields, so we don't overwrite existing values
  // with blanks just because the form field was left empty; password keeps "" as a
  // deliberate "clear it" signal (the backend treats that specially).
  return {
    name: form.name,
    rtsp_url: form.rtsp_url,
    username: form.username || null,
    password: form.password,
    location_label: form.location_label || null,
    notes: form.notes || null,
  };
}

function CameraForm({
  initial,
  submitLabel,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  initial: CameraCreateRequest;
  submitLabel: string;
  busy: boolean;
  error: string | null;
  onSubmit: (form: CameraCreateRequest) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState(initial);

  function set<K extends keyof CameraCreateRequest>(key: K, value: CameraCreateRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <form
      className="camera-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(toUpdatePayload(form));
      }}
    >
      <div className="settings-row">
        <label htmlFor="camera-name">Name</label>
        <input
          id="camera-name"
          type="text"
          required
          value={form.name}
          onChange={(e) => set("name", e.currentTarget.value)}
        />
      </div>
      <div className="settings-row">
        <label htmlFor="camera-rtsp-url">RTSP URL</label>
        <input
          id="camera-rtsp-url"
          type="text"
          required
          placeholder="rtsp://192.168.1.50:554/stream1"
          value={form.rtsp_url}
          onChange={(e) => set("rtsp_url", e.currentTarget.value)}
        />
      </div>
      <div className="row">
        <div className="settings-row">
          <label htmlFor="camera-username">Username</label>
          <input
            id="camera-username"
            type="text"
            value={form.username ?? ""}
            onChange={(e) => set("username", e.currentTarget.value)}
          />
        </div>
        <div className="settings-row">
          <label htmlFor="camera-password">Password</label>
          <input
            id="camera-password"
            type="password"
            placeholder={submitLabel === "Save changes" ? "Leave blank to keep current" : ""}
            value={form.password ?? ""}
            onChange={(e) => set("password", e.currentTarget.value)}
          />
        </div>
      </div>
      <div className="settings-row">
        <label htmlFor="camera-location">Location</label>
        <input
          id="camera-location"
          type="text"
          placeholder="e.g. Warehouse — Loading Dock"
          value={form.location_label ?? ""}
          onChange={(e) => set("location_label", e.currentTarget.value)}
        />
      </div>
      <div className="settings-row">
        <label htmlFor="camera-notes">Notes</label>
        <input
          id="camera-notes"
          type="text"
          value={form.notes ?? ""}
          onChange={(e) => set("notes", e.currentTarget.value)}
        />
      </div>

      {error && <ErrorNotice message={error} />}

      <div className="row">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Saving..." : submitLabel}
        </Button>
        <Button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function CameraRow({ camera }: { camera: Camera }) {
  const [editing, setEditing] = useState(false);
  const updateCamera = useUpdateCamera();
  const deleteCamera = useDeleteCamera();
  const testConnection = useTestCameraConnection();

  if (editing) {
    return (
      <li className="camera-row">
        <CameraForm
          initial={{
            name: camera.name,
            rtsp_url: camera.rtsp_url,
            username: camera.username ?? "",
            password: "",
            location_label: camera.location_label ?? "",
            notes: camera.notes ?? "",
          }}
          submitLabel="Save changes"
          busy={updateCamera.isPending}
          error={updateCamera.isError ? updateCamera.error.message : null}
          onSubmit={(body) =>
            updateCamera.mutate(
              { id: camera.id, body },
              { onSuccess: () => setEditing(false) },
            )
          }
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  // Show the mutation's own result immediately rather than waiting for the list to
  // refetch after invalidation — otherwise a just-run test's outcome doesn't appear
  // until that refetch resolves, which is a visible lag from the user's perspective.
  const displayCamera = testConnection.data ?? camera;

  return (
    <li className="camera-row">
      <div className="camera-row__header">
        <div>
          <strong>{camera.name}</strong>{" "}
          <StatusBadge
            label={displayCamera.connection_status}
            tone={STATUS_TONE[displayCamera.connection_status]}
          />
        </div>
        <div className="row">
          <Button onClick={() => testConnection.mutate(camera.id)} disabled={testConnection.isPending}>
            {testConnection.isPending ? "Testing..." : "Test connection"}
          </Button>
          <Button onClick={() => setEditing(true)}>Edit</Button>
          <Button
            onClick={() => {
              if (window.confirm(`Delete camera "${camera.name}"? This cannot be undone.`)) {
                deleteCamera.mutate(camera.id);
              }
            }}
            disabled={deleteCamera.isPending}
          >
            Delete
          </Button>
        </div>
      </div>

      <div className="camera-row__details">
        <code>{camera.rtsp_url}</code>
        {camera.location_label && <span> · {camera.location_label}</span>}
        {camera.has_password && <span> · credentials saved</span>}
      </div>

      {displayCamera.last_tested_at && (
        <p className="camera-row__test-result">
          Last tested {new Date(displayCamera.last_tested_at).toLocaleString()}
          {displayCamera.connection_status === "online" && displayCamera.last_width && displayCamera.last_height && (
            <>
              {" "}
              — {displayCamera.last_width}×{displayCamera.last_height}
              {displayCamera.last_fps ? ` @ ${displayCamera.last_fps.toFixed(1)} fps` : ""}
            </>
          )}
        </p>
      )}
      {displayCamera.connection_status === "offline" && displayCamera.last_error && (
        <ErrorNotice message={displayCamera.last_error} />
      )}
      {testConnection.isError && <ErrorNotice message={testConnection.error.message} />}
      {deleteCamera.isError && <ErrorNotice message={deleteCamera.error.message} />}
    </li>
  );
}

export function CamerasPage() {
  const { data: cameras, isLoading, isError, error } = useCameras();
  const createCamera = useCreateCamera();
  const [adding, setAdding] = useState(false);

  return (
    <Card title="Cameras">
      <div className="row">
        {!adding && <Button variant="primary" onClick={() => setAdding(true)}>Add camera</Button>}
      </div>

      {adding && (
        <CameraForm
          initial={EMPTY_FORM}
          submitLabel="Add camera"
          busy={createCamera.isPending}
          error={createCamera.isError ? createCamera.error.message : null}
          onSubmit={(body) => createCamera.mutate(body, { onSuccess: () => setAdding(false) })}
          onCancel={() => setAdding(false)}
        />
      )}

      {isLoading && <Spinner label="Loading cameras" />}
      {isError && <ErrorNotice message={error.message} />}

      {cameras && cameras.length === 0 && !adding && (
        <EmptyState title="No cameras yet">Add your first camera to get started.</EmptyState>
      )}

      {cameras && cameras.length > 0 && (
        <ul className="camera-list">
          {cameras.map((camera) => (
            <CameraRow key={camera.id} camera={camera} />
          ))}
        </ul>
      )}
    </Card>
  );
}
