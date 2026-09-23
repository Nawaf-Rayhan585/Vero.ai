# Vero.ai — Architecture

**Status:** Target architecture (not yet implemented). The current codebase is a single-machine prototype — see [ROADMAP.md](ROADMAP.md) for what actually exists today.

## High-level target architecture

```
                     Vero.ai Cloud
                          │
           ┌──────────────┼──────────────┐
           │              │              │
         Auth          Licensing      Analytics
           │              │              │
           └──────────────┼──────────────┘
                          │
                     PostgreSQL
                          │
                     REST API
                          │
                ┌─────────┴─────────┐
                │                   │
          Own Hardware          Vero Cloud
                │                   │
          Local AI Engine      Cloud AI Engine
                │                   │
                └─────────┬─────────┘
                          │
                     CCTV / RTSP
```

### Own Hardware data flow

CCTV → local camera manager → local AI engine → local analytics/events → secure cloud sync (structured data only)

### Vero Cloud data flow

CCTV → Vero cloud ingestion → cloud AI engine → analytics/events → customer dashboard

Raw video is not automatically persisted in cloud storage under either plan.

## Data model direction

Multi-tenant hierarchy, in a single shared PostgreSQL database using tenant/org IDs and authorization boundaries — **not** one database per customer:

```
User → Organization → Location → Camera → AI Modules → Events / Analytics
```

Must support: one user across multiple organizations where appropriate, multiple locations, multiple cameras per location, different AI modules enabled per camera, different plan limits per organization/plan.

**Implemented in Phase 10:** `User → Organization → Location → Camera`, Owner/Admin/Member roles, and one user belonging to several organizations — but in *this same local backend and PostgreSQL*, not the separate "Vero.ai Cloud" box in the diagram above, which doesn't exist yet. The auth code (`backend/app/security.py`, `app/auth.py`) is kept in its own modules so it can move without rewriting the rest of the backend. Whether an Own Hardware customer's accounts stay local, move to the cloud, or sync between the two is an open decision for **Phase 13** (Phase 12 deliberately left them local — see below).

**Implemented in Phase 11:** the "different plan limits per organization/plan" requirement above now has a real mechanism — each organization has one `Subscription` row (`status`, `plan_type`, `trial_ends_at`, `max_cameras`), and the enforcement boundary between the Auth/Licensing boxes in the diagram and the rest of the API is `require_active_configurator` (`app/auth.py`), which the *growth* subset of configure endpoints depend on. The diagram's separate "Licensing" cloud box still doesn't exist — like accounts, this lives in the local backend for now — and `plan_type`/`max_cameras` don't yet change any actual behavior, since Phases 12-14 haven't defined what Own Hardware vs. Vero Cloud or real entitlement numbers mean yet.

**Implemented in Phase 12:** device entitlement — `Subscription.max_devices` and a `Device` row per registered machine (`app/models.py`, `routers/devices.py`) — is the one Own Hardware-specific concept `PROJECT.md` names ("possibly device entitlement") that Phases 1-11 hadn't touched; everything else the Own Hardware plan actually is (local camera manager, local AI engine, local accounts, a local licensing check) was already built by Phase 11. A device is deliberately a soft record (a name, not a hardware fingerprint), and `plan_type` still doesn't gate anything — any organization, regardless of chosen plan, can register devices today. Real hardware-binding, and whether Vero Cloud needs its own differentiated limits, remain open (Phase 13/16).

**Implemented in Phase 13:** `plan_type == "vero_cloud"` now genuinely changes behavior — the "Cloud AI Engine" box in the diagram above is real: a new, separate service (`cloud-engine/`, its own FastAPI app) imports `backend/app/tracking.py` and its dependencies directly (the same `sys.path` import trick `backend/app/detection_runner.py` already uses for `ai-engine/`) and runs a Vero Cloud organization's camera tracking, reached only by `backend` itself over an internal-secret-authenticated HTTP call (`app/cloud_routing.py`), never by the desktop app or the internet. It is a second process, not a rewrite: `backend`'s existing local tracking code is completely unchanged and still runs every Own Hardware organization's cameras exactly as before. Crucially, `cloud-engine` is **not** a separate deployment with its own database — it shares `backend`'s same PostgreSQL database (this section's "single shared PostgreSQL database... not one database per customer" principle applies across services too, not just across tenants), so events, heat snapshots and analytics computed from a Vero Cloud camera's activity are indistinguishable, from any read endpoint's perspective, from an Own Hardware camera's. What the diagram's "Vero cloud ingestion" box implies (camera reachability from the cloud side, e.g. behind a customer's NAT) is **not** built — `cloud-engine` opens the camera's RTSP URL directly, exactly like `backend` does, so today it only works for a camera `cloud-engine`'s own host can already reach. The "Vero.ai Cloud" box (Auth/Licensing) remains unimplemented as its own service — accounts and subscriptions are still served by `backend` for both plans, unchanged; see `ROADMAP.md`'s open items for that still-open decision.

## Camera architecture

Per camera: RTSP URL, name, location, credentials, connection testing, connection status, reconnection, per-camera AI module selection, per-camera settings, FPS/resolution handling, live preview where practical. Camera streams are not assumed identical.

Must handle: camera offline, RTSP timeout, invalid credentials, network interruption, reconnection, stream unavailable, high CPU usage, high GPU usage.

## AI engine architecture

Modular — no single monolithic detector file. Conceptual module layout (exact structure decided during the relevant phase):

```
AI Engine
├── camera/
├── detection/
├── tracking/
├── counting/
├── zones/
├── heatmap/
├── ocr/
├── qr/
├── barcode/
├── analytics/
├── events/
└── pipeline/
```

Pipeline: Detection → Tracking → Feature logic → Event generation → Analytics aggregation → Cloud synchronization. Detection is kept separate from business logic so new AI modules can be added without rewriting the system.

## Events vs. raw video

Normal operation sends structured events to the cloud, not video frames. Examples:

- **Person entered**: `camera_id`, `timestamp`, `direction`
- **Daily analytics**: `camera_id`, `date`, `people_entered`, `people_exited`, `vehicle_count`
- **Zone event**: `camera_id`, `zone_id`, `timestamp`, `event_type`
- **OCR event**: `camera_id`, `timestamp`, `detected_text`

### Event schema (designed in Phase 9)

Events are stored locally in PostgreSQL, in one flat `events` table. They are flat columns rather than a JSON blob because analytics group by these fields, and a flat row is what a later cloud sync will send. An event never holds video or images.

| Column | Meaning |
|---|---|
| `id` | UUID |
| `camera_id` | The camera. Deleting a camera deletes its events (like its lines and zones). |
| `occurred_at` | When it happened (timestamp with time zone). |
| `event_type` | `line_crossed`, `zone_entered`, `zone_exited`, `read`, `tracking_started`, `tracking_stopped`, `tracking_error`, `tracking_reconnecting`, `tracking_resumed` |
| `category` | `person` or `vehicle` for crossings and zone events; `qr`, `barcode` or `ocr` for reads |
| `direction` | `in` or `out` (line crossings) |
| `subject_id`, `subject_name` | The line or zone concerned. Deliberately *not* a foreign key: a line or zone can be deleted later, and the history keeps the name it had at the time. |
| `value` | The text read, or an error message |
| `detail` | The code's symbology (e.g. "Code 128") or the OCR confidence |

How the examples above map onto it: "Person entered" is a `line_crossed` event (`category` person, `direction` in); the "Zone event" is `zone_entered` / `zone_exited`; the "OCR event" is a `read` event (`category` ocr, `value` the detected text). "Daily analytics" is deliberately **not** a stored record: totals and trends are computed on demand from the events (`/analytics/summary`, `/analytics/timeseries`), so there is a single source of truth and nothing to fall out of sync. The `tracking_*` events record when a camera was actually being watched, which is what lets a chart tell "nobody came" from "not running".

A `read` is one event per *sighting* — the first time a value is seen, or again after a short gap — not one per frame it stays in view. A zone `entered` is a visit: someone hidden for more than about five seconds and then reappearing counts again.

Heat is stored separately in `heatmap_snapshots`: one row per camera per UTC hour, holding a small compressed grid of where people stood (about 1 KB), merged as more accumulates. Historical heatmaps are drawn from these, over a fresh camera snapshot when the camera answers or a plain background when it doesn't. No video frame is stored.

Delivery is **at-most-once**: events pass through a bounded in-memory queue, so a hard crash can lose the last second or so, a database outage is retried but not indefinitely, and the writer never blocks or crashes tracking.

## Technology stack

- **Desktop:** Tauri v2, React, TypeScript, Vite
- **AI:** Python, Ultralytics YOLO, OpenCV, FFmpeg (where required), ByteTrack or an appropriate tracker, PaddleOCR or an appropriate OCR solution, appropriate QR/barcode decoders
- **Backend:** Python, FastAPI, REST API
- **Database:** PostgreSQL — the single database technology for the whole project. No per-plan or per-mode substitution (e.g. no SQLite variant for local/offline mode) unless explicitly re-approved by the project owner.
- **ORM/migrations:** SQLAlchemy + Alembic, unless a strong documented reason exists to choose otherwise
- **Auth:** JWT/session-based, secure password hashing, secure token storage
- **Payments:** PayPal
- **Packaging:** Tauri Windows installer; the local backend/AI engine must eventually be packaged or managed automatically — end users should never need to manually run Uvicorn or Python
- **VCS:** Git / GitHub

## Security requirements (target)

HTTPS in production, secure authentication, password hashing, secure tokens, API authorization, organization isolation, camera credential protection, input validation, rate limiting, secure webhook verification, license validation, secrets kept outside source code, safe logging, no raw video upload by default. Never hard-code production credentials.
