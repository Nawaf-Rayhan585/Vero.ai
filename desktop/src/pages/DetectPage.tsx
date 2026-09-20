import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { open } from "@tauri-apps/plugin-dialog";
import { jobsApi } from "../api/jobs";
import { useJob } from "../hooks/useJob";
import { useSettings } from "../settings/SettingsContext";
import { Button, Card, ErrorNotice, Spinner } from "../components/ui";
import type { ModelType } from "../api/types";

export function DetectPage() {
  const settings = useSettings();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const jobId = searchParams.get("job");

  const [filePath, setFilePath] = useState("");
  const [modelType, setModelType] = useState<ModelType>(settings.defaultModelType);
  const [confidenceThreshold, setConfidenceThreshold] = useState(settings.defaultConfidenceThreshold);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const { data: job, error: jobError } = useJob(jobId);
  const isBusy = job !== undefined && (job?.status === "pending" || job?.status === "running");

  async function selectFile() {
    setErrorMsg("");
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: "Media", extensions: ["jpg", "jpeg", "png", "bmp", "mp4", "avi", "mov", "mkv"] }],
      });
      if (typeof selected === "string") setFilePath(selected);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to open file dialog");
    }
  }

  async function submitJob() {
    if (!filePath) {
      setErrorMsg("Select a video or image file first.");
      return;
    }
    setErrorMsg("");
    setSubmitting(true);
    try {
      const { id } = await jobsApi.create({
        video_source: filePath,
        model_type: modelType,
        confidence_threshold: confidenceThreshold,
      });
      setSearchParams({ job: id });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? `Could not reach backend: ${err.message}` : "Could not reach backend",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <div className="row">
        <Button onClick={selectFile} disabled={isBusy}>
          Select Video/Image
        </Button>
        <span>{filePath || "No file selected"}</span>
      </div>

      <div className="row">
        <label htmlFor="detect-model-select">Model</label>
        <select
          id="detect-model-select"
          value={modelType}
          onChange={(e) => setModelType(e.currentTarget.value as ModelType)}
          disabled={isBusy}
        >
          <option value="yolo">YOLO (detection)</option>
          <option value="yolo_seg">YOLO (segmentation)</option>
          <option value="yolo_pose">YOLO (pose)</option>
        </select>
        <label htmlFor="detect-conf-slider">Confidence: {confidenceThreshold.toFixed(2)}</label>
        <input
          id="detect-conf-slider"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={confidenceThreshold}
          onChange={(e) => setConfidenceThreshold(Number(e.currentTarget.value))}
          disabled={isBusy}
        />
      </div>

      <div className="row">
        <Button variant="primary" onClick={submitJob} disabled={submitting || isBusy || !filePath}>
          {submitting || isBusy ? "Processing..." : "Run Detection"}
        </Button>
        {isBusy && <Spinner />}
      </div>

      {errorMsg && <ErrorNotice message={errorMsg} />}
      {jobError && <ErrorNotice message={jobError instanceof Error ? jobError.message : "Failed to load job"} />}

      {job && (
        <section className="results">
          <p>
            Job <code>{job.id}</code> — status: <strong>{job.status}</strong>
          </p>

          {job.status === "failed" && <ErrorNotice message={`Error: ${job.error}`} />}

          {job.status === "completed" && job.result?.detections && (
            <ul>
              {job.result.detections.map((d, i) => (
                <li key={i}>
                  {d.label} — {(d.confidence * 100).toFixed(1)}% — box [{d.box.map((n) => n.toFixed(0)).join(", ")}]
                </li>
              ))}
              {job.result.detections.length === 0 && <li>No objects detected.</li>}
            </ul>
          )}

          {job.status === "completed" && job.result?.frames && <p>{job.result.frames.length} frame(s) processed.</p>}
        </section>
      )}
    </Card>
  );
}
