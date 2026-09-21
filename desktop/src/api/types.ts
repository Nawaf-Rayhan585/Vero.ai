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

/** The AI modules a camera can run — ids match the backend (app/modules.py). */
export type AIModule = "people" | "vehicles" | "ocr" | "qr" | "barcode";

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
  enabled_modules: AIModule[];
}

export interface CameraCreateRequest {
  name: string;
  rtsp_url: string;
  username?: string | null;
  password?: string | null;
  location_label?: string | null;
  notes?: string | null;
  enabled_modules?: AIModule[];
}

export type CameraUpdateRequest = Partial<CameraCreateRequest>;

export type TrackingStatusValue = "starting" | "running" | "reconnecting" | "error" | "stopped";

export interface LineCount {
  line_id: string;
  name: string;
  /** People. Vehicles are counted separately below. */
  in_count: number;
  out_count: number;
  vehicle_in_count: number;
  vehicle_out_count: number;
}

/** One thing a reading module has seen this session, deduplicated by kind + value.
 * Ephemeral — not an event and not stored (that is a later phase). */
export interface Read {
  kind: AIModule;
  value: string;
  /** Symbology for QR/barcode ("QR Code", "Code 128"); OCR confidence (0-1) for text. */
  detail: string;
  first_seen_at: string;
  last_seen_at: string;
  sightings: number;
}

export interface ZoneCount {
  zone_id: string;
  name: string;
  count: number;
}

export interface TrackingStatus {
  status: TrackingStatusValue;
  error: string | null;
  frame_count: number;
  started_at: string | null;
  last_frame_at: string | null;
  active_track_ids: number[];
  active_vehicle_track_ids: number[];
  line_counts: LineCount[];
  zone_counts: ZoneCount[];
  reads: Read[];
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

/** Normalized 0-1 against the camera frame, like Line's coordinates. */
export interface ZonePoint {
  x: number;
  y: number;
}

export interface Zone {
  id: string;
  camera_id: string;
  name: string;
  points: ZonePoint[];
  created_at: string;
}

export interface ZoneCreateRequest {
  name: string;
  points: ZonePoint[];
}
