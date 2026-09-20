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

Exact schema is designed in a later phase.

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
