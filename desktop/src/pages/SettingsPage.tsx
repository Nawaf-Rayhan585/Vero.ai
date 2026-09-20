import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { isValidBaseUrl } from "../api/config";
import { ApiError, NetworkError } from "../api/client";
import { useSettings } from "../settings/SettingsContext";
import { Button, Card, ErrorNotice } from "../components/ui";
import type { ModelType } from "../api/types";

type ConnectionTestState =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok" }
  | { status: "error"; message: string };

export function SettingsPage() {
  const settings = useSettings();
  const queryClient = useQueryClient();
  const [urlDraft, setUrlDraft] = useState(settings.apiBaseUrl);
  const [urlError, setUrlError] = useState("");
  const [testState, setTestState] = useState<ConnectionTestState>({ status: "idle" });

  // The Dashboard/TopBar poll health on a timer; without this they'd keep showing the
  // old server's last-known status for up to that interval after the URL changes here.
  function recheckConnectivity() {
    queryClient.invalidateQueries({ queryKey: ["health"] });
  }

  function saveUrl() {
    if (!isValidBaseUrl(urlDraft)) {
      setUrlError("Enter a valid http(s) URL, e.g. http://127.0.0.1:8000");
      return;
    }
    setUrlError("");
    settings.setApiBaseUrl(urlDraft);
    recheckConnectivity();
  }

  function resetUrl() {
    settings.setApiBaseUrl(null);
    recheckConnectivity();
    setUrlDraft(settings.defaultApiBaseUrl);
    setUrlError("");
    setTestState({ status: "idle" });
  }

  async function testConnection() {
    setTestState({ status: "testing" });
    const candidate = urlDraft.replace(/\/$/, "");
    try {
      const response = await fetch(`${candidate}/health`, { signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new ApiError(response.status, response.statusText);
      setTestState({ status: "ok" });
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof NetworkError
          ? err.message
          : "Could not reach that address";
      setTestState({ status: "error", message });
    }
  }

  return (
    <>
      <Card title="Detection defaults">
        <div className="settings-row">
          <label htmlFor="model-select">Default model</label>
          <select
            id="model-select"
            value={settings.defaultModelType}
            onChange={(e) => settings.setDefaultModelType(e.currentTarget.value as ModelType)}
          >
            <option value="yolo">YOLO (detection)</option>
            <option value="yolo_seg">YOLO (segmentation)</option>
            <option value="yolo_pose">YOLO (pose)</option>
          </select>
        </div>
        <div className="settings-row">
          <label htmlFor="conf-slider">
            Default confidence threshold: {settings.defaultConfidenceThreshold.toFixed(2)}
          </label>
          <input
            id="conf-slider"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={settings.defaultConfidenceThreshold}
            onChange={(e) => settings.setDefaultConfidenceThreshold(Number(e.currentTarget.value))}
          />
        </div>
      </Card>

      <Card title="Backend connection">
        <div className="settings-row">
          <label htmlFor="backend-url">Backend URL</label>
          <input
            id="backend-url"
            type="text"
            value={urlDraft}
            onChange={(e) => {
              setUrlDraft(e.currentTarget.value);
              setTestState({ status: "idle" });
            }}
            placeholder={settings.defaultApiBaseUrl}
          />
        </div>
        {urlError && <ErrorNotice message={urlError} />}
        {testState.status === "ok" && <p style={{ color: "var(--color-success)" }}>Connected successfully.</p>}
        {testState.status === "error" && <ErrorNotice message={testState.message} />}
        <div className="row">
          <Button onClick={testConnection} disabled={testState.status === "testing"}>
            {testState.status === "testing" ? "Testing..." : "Test connection"}
          </Button>
          <Button variant="primary" onClick={saveUrl}>
            Save
          </Button>
          <Button onClick={resetUrl}>Reset to default</Button>
        </div>
      </Card>
    </>
  );
}
