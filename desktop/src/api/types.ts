export type ModelType = "yolo" | "yolo_seg" | "yolo_pose";

export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface Detection {
  label: string;
  confidence: number;
  box: [number, number, number, number];
}

export interface JobResult {
  type: "image" | "video";
  detections?: Detection[];
  frames?: { frame: number; detections: Detection[] }[];
}

export interface Job {
  id: string;
  video_source: string;
  model_type: ModelType;
  confidence_threshold: number;
  status: JobStatus;
  created_at: string;
  result: JobResult | null;
  error: string | null;
}

export interface CreateJobRequest {
  video_source: string;
  model_type: ModelType;
  confidence_threshold: number;
}

export type ConnectionStatus = "unknown" | "online" | "offline";

export interface Camera {
  id: string;
  name: string;
  rtsp_url: string;
  username: string | null;
  has_password: boolean;
  location_label: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  connection_status: ConnectionStatus;
  last_tested_at: string | null;
  last_error: string | null;
  last_fps: number | null;
  last_width: number | null;
  last_height: number | null;
}

export interface CameraCreateRequest {
  name: string;
  rtsp_url: string;
  username?: string | null;
  password?: string | null;
  location_label?: string | null;
  notes?: string | null;
}

export type CameraUpdateRequest = Partial<CameraCreateRequest>;

export type TrackingStatusValue = "starting" | "running" | "reconnecting" | "error" | "stopped";

export interface LineCount {
  line_id: string;
  name: string;
  in_count: number;
  out_count: number;
}

export interface TrackingStatus {
  status: TrackingStatusValue;
  error: string | null;
  frame_count: number;
  started_at: string | null;
  last_frame_at: string | null;
  active_track_ids: number[];
  line_counts: LineCount[];
}

export interface Line {
  id: string;
  camera_id: string;
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  created_at: string;
}

export interface LineCreateRequest {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
