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
  location_id: string;
  location_name: string;
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
  /** Omit to use the organization's default location. */
  location_id?: string | null;
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

export type EventType =
  | "line_crossed"
  | "zone_entered"
  | "zone_exited"
  | "read"
  | "tracking_started"
  | "tracking_stopped"
  | "tracking_error"
  | "tracking_reconnecting"
  | "tracking_resumed";

/** One stored event. The backend calls it an Event; AppEvent avoids clashing with the DOM's. */
export interface AppEvent {
  id: string;
  camera_id: string;
  camera_name: string;
  occurred_at: string;
  event_type: EventType;
  /** "person" / "vehicle" for crossings and zones; "qr" / "barcode" / "ocr" for reads. */
  category: string | null;
  direction: string | null;
  subject_id: string | null;
  subject_name: string | null;
  value: string | null;
  detail: string | null;
}

export interface EventList {
  events: AppEvent[];
  /** Pass back as `before` for the next (older) page; null on the last page. */
  next_before: string | null;
}

export interface LineSummary {
  line_id: string | null;
  name: string | null;
  people_in: number;
  people_out: number;
  vehicle_in: number;
  vehicle_out: number;
}

export interface ZoneSummary {
  zone_id: string | null;
  name: string | null;
  entered: number;
  exited: number;
}

export interface AnalyticsSummary {
  since: string;
  until: string;
  people_in: number;
  people_out: number;
  vehicle_in: number;
  vehicle_out: number;
  lines: LineSummary[];
  zones: ZoneSummary[];
  reads: { qr: number; barcode: number; ocr: number };
  /** Camera-seconds tracking was actually running in the range (summed over cameras). */
  tracked_seconds: number;
}

export interface TimeseriesPoint {
  start: string;
  end: string;
  people_in: number;
  people_out: number;
  vehicle_in: number;
  vehicle_out: number;
  zone_entered: number;
  zone_exited: number;
  reads: number;
  /** 0 means nothing was being tracked: "not running", not "no traffic". */
  tracked_seconds: number;
}

export interface Timeseries {
  bucket: "hour" | "day";
  tz: string;
  since: string;
  until: string;
  points: TimeseriesPoint[];
}

export interface HeatmapInfo {
  camera_id: string;
  available: boolean;
  samples: number;
  frame_width: number | null;
  frame_height: number | null;
  grid_width: number | null;
  grid_height: number | null;
  first_period: string | null;
  last_period: string | null;
  ignored_samples: number;
}

// -- Auth, organizations, locations, members (Phase 10) ---------------------------------

export type Role = "owner" | "admin" | "member";

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  created_at: string;
}

export interface OrganizationMembership {
  organization: Organization;
  role: Role;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  /** Seconds until the access token expires. */
  expires_in: number;
  user: User;
  organizations: OrganizationMembership[];
}

export interface MeResponse {
  user: User;
  organizations: OrganizationMembership[];
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  organization_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface Location {
  id: string;
  organization_id: string;
  name: string;
  timezone: string;
  camera_count: number;
  created_at: string;
}

export interface LocationCreateRequest {
  name: string;
  timezone?: string;
}

export type LocationUpdateRequest = Partial<LocationCreateRequest>;

export interface Member {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  created_at: string;
}

export interface MemberAddRequest {
  email: string;
  role?: Role;
}
