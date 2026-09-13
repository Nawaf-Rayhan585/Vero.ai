import { useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

type ModelType = "yolo" | "yolo_seg" | "yolo_pose";

type JobStatus = "pending" | "running" | "completed" | "failed";

type Screen = "detect" | "settings";

interface Detection {
  label: string;
  confidence: number;
  box: [number, number, number, number];
}

interface Job {
  id: string;
  video_source: string;
  model_type: ModelType;
  confidence_threshold: number;
  status: JobStatus;
  created_at: string;
  result: { type: "image" | "video"; detections?: Detection[]; frames?: unknown[] } | null;
  error: string | null;
}

function App() {
  const [screen, setScreen] = useState<Screen>("detect");
  const [filePath, setFilePath] = useState<string>("");
  const [modelType, setModelType] = useState<ModelType>("yolo");
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(0.25);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const isBusy = job !== null && (job.status === "pending" || job.status === "running");

  async function selectFile() {
    setErrorMsg("");
    try {
      const selected = await open({
        multiple: false,
        filters: [
          { name: "Media", extensions: ["jpg", "jpeg", "png", "bmp", "mp4", "avi", "mov", "mkv"] },
        ],
      });
      if (typeof selected === "string") {
        setFilePath(selected);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to open file dialog");
    }
  }

  function pollJob(jobId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`);
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const data: Job = await res.json();
        setJob(data);
        if (data.status === "completed" || data.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (err) {
        setErrorMsg(
          err instanceof Error
            ? `Lost connection to backend: ${err.message}`
            : "Lost connection to backend"
        );
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 1500);
  }

  async function submitJob() {
    if (!filePath) {
      setErrorMsg("Select a video or image file first.");
      return;
    }
    setErrorMsg("");
    setSubmitting(true);
    setJob(null);
    try {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_source: filePath,
          model_type: modelType,
          confidence_threshold: confidenceThreshold,
        }),
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const { id } = await res.json();
      setJob({
        id,
        video_source: filePath,
        model_type: modelType,
        confidence_threshold: confidenceThreshold,
        status: "pending",
        created_at: new Date().toISOString(),
        result: null,
        error: null,
      });
      pollJob(id);
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? `Could not reach backend: ${err.message}`
          : "Could not reach backend"
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="container">
      <nav className="row nav-row">
        <button
          className={screen === "detect" ? "nav-active" : ""}
          onClick={() => setScreen("detect")}
        >
          Detect
        </button>
        <button
          className={screen === "settings" ? "nav-active" : ""}
          onClick={() => setScreen("settings")}
        >
          Settings
        </button>
      </nav>

      {screen === "settings" && (
        <section className="panel">
          <h2>Settings</h2>
          <div className="row">
            <label htmlFor="model-select">Default model:</label>
            <select
              id="model-select"
              value={modelType}
              onChange={(e) => setModelType(e.currentTarget.value as ModelType)}
            >
              <option value="yolo">YOLO (detection)</option>
              <option value="yolo_seg">YOLO (segmentation)</option>
              <option value="yolo_pose">YOLO (pose)</option>
            </select>
          </div>
          <div className="row">
            <label htmlFor="conf-slider">
              Confidence threshold: {confidenceThreshold.toFixed(2)}
            </label>
            <input
              id="conf-slider"
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(Number(e.currentTarget.value))}
            />
          </div>
        </section>
      )}

      {screen === "detect" && (
        <section className="panel">
          <div className="row">
            <button onClick={selectFile} disabled={isBusy}>
              Select Video/Image
            </button>
            <span>{filePath || "No file selected"}</span>
          </div>

          <div className="row">
            <button onClick={submitJob} disabled={submitting || isBusy || !filePath}>
              {submitting || isBusy ? "Processing..." : "Run Detection"}
            </button>
            {isBusy && <span className="spinner" aria-label="loading" />}
          </div>

          {errorMsg && <p className="error-text">{errorMsg}</p>}

          {job && (
            <section className="results">
              <p>
                Job <code>{job.id}</code> — status: <strong>{job.status}</strong>
              </p>

              {job.status === "failed" && (
                <p className="error-text">Error: {job.error}</p>
              )}

              {job.status === "completed" && job.result?.detections && (
                <ul>
                  {job.result.detections.map((d, i) => (
                    <li key={i}>
                      {d.label} — {(d.confidence * 100).toFixed(1)}% — box [
                      {d.box.map((n) => n.toFixed(0)).join(", ")}]
                    </li>
                  ))}
                  {job.result.detections.length === 0 && <li>No objects detected.</li>}
                </ul>
              )}

              {job.status === "completed" && job.result?.frames && (
                <p>{job.result.frames.length} frame(s) processed.</p>
              )}
            </section>
          )}
        </section>
      )}
    </main>
  );
}

export default App;
