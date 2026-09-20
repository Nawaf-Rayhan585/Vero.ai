# Vero.ai

Desktop app for running YOLO-based object detection/segmentation/pose estimation on images and videos.

This is a working prototype, not the V1 product. See [docs/PROJECT.md](docs/PROJECT.md) for the product spec and [docs/ROADMAP.md](docs/ROADMAP.md) for the official phase-by-phase roadmap.

## Architecture

- **backend/** — FastAPI server. Jobs, cameras, and entry/exit lines are stored in PostgreSQL (SQLAlchemy + Alembic migrations); exposes `/jobs`, `/cameras`, and `/cameras/{id}/lines` endpoints. Camera passwords are encrypted at rest (`app/crypto.py`, Fernet); RTSP connectivity testing and snapshot grabbing (`app/camera_testing.py`) use OpenCV with a bounded timeout. Continuous person detection + tracking (`app/tracking.py`, Ultralytics YOLO + ByteTrack) runs one background thread per actively-tracked camera; entry/exit line-crossing counting (`app/counting.py`, pure geometry) runs inside that same loop. Session state — frame count, active tracks, in/out counts — is fully in-memory, reset every time tracking starts; only the line *definitions* are persisted.
- **ai-engine/** — YOLO detection pipeline (`Detector` class). Imported directly by `backend/` (not a separate service).
- **desktop/** — Tauri + React UI, structured for the full app: `src/app/routes.tsx` is the single source of truth for the sidebar and router, `src/api/` is the typed backend client, `src/pages/` holds one component per section (Dashboard, Detect, Settings; the rest are honest placeholders naming the phase that builds them), `src/hooks/` wraps the API in React Query, `src/settings/` persists user preferences (including the backend URL) to `localStorage`. Talks to the backend over HTTP at `http://127.0.0.1:8000` by default — overridable per-machine from the in-app Settings page (Backend connection).

## Prerequisites

- Python 3.10+
- Node.js 18+
- Rust toolchain (for Tauri) — see https://tauri.app/start/prerequisites/
- Docker Desktop (runs the local PostgreSQL container)

## First-time setup

```powershell
# Database config + PostgreSQL (from the repo root)
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai"
Copy-Item .env.example .env
# Edit .env: set a real POSTGRES_PASSWORD (and matching DATABASE_URL), and a real
# CAMERA_CREDENTIALS_KEY — generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# .env is gitignored. Losing/changing CAMERA_CREDENTIALS_KEY makes stored camera
# passwords unrecoverable.
docker compose up -d postgres --wait

# Backend (also covers ai-engine's dependencies, since backend imports it directly)
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
alembic upgrade head
deactivate

# Desktop
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\desktop"
npm install
```

## Running the app (development)

PostgreSQL must be running (`docker compose up -d postgres --wait` from the repo root; Docker Desktop must be started first). It listens on `127.0.0.1:5433` — not 5432 — so it does not clash with other local Postgres instances.

Run these in two separate PowerShell terminals.

```powershell
# Terminal 1 — backend API
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\backend"
.\venv\Scripts\Activate.ps1
alembic upgrade head
python -m uvicorn main:app --reload --port 8000
```

```powershell
# Terminal 2 — desktop app
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\desktop"
npm run tauri dev
```

Or use the bundled start script, which starts PostgreSQL, launches the backend (applying migrations) in a new window, and then starts the desktop dev app:

```powershell
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai"
.\start-dev.ps1
```

Once both are running: click **Select Video/Image** in the app, choose a model and confidence threshold under **Settings**, then click **Run Detection**. Add a camera under **Cameras** (an RTSP URL, or a local video file path for testing without real camera hardware) and use **Test connection**; **Live View** shows a refreshing snapshot from the selected camera. Under **AI Modules**, click **Lines** to draw an entry/exit line (click two points directly on the camera image, name it, save), then click **Start tracking** to run continuous person detection + tracking + line counting — while it's running, Live View for that camera automatically switches to the AI-annotated feed, with lines and live in/out counts burned into the video itself.

The first detection run for a given model downloads its YOLO weights (e.g. `yolov8n.pt`) into `backend/` and caches them there for subsequent runs.

## Running the backend tests

PostgreSQL must be running. Tests use a separate `vero_test` database (created automatically) and never touch the dev database. They include real YOLO inference, so the first run takes a few seconds longer.

```powershell
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\backend"
.\venv\Scripts\Activate.ps1
python -m pytest -v
```

If PostgreSQL is not reachable the suite stops immediately with instructions — it never silently skips database tests.

## Running the desktop tests

```powershell
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\desktop"
npm test
```

Vitest + Testing Library; no backend or PostgreSQL required, since the API layer is mocked in these tests.

## Building a Windows installer

```powershell
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\desktop"
npm run tauri build
```

This produces an MSI and an NSIS installer under `desktop/src-tauri/target/release/bundle/`. The bundled app expects the backend to be running separately at `http://127.0.0.1:8000` — it does not launch or embed the Python backend.

## Notes / current limitations (V1)

- Job history is stored in PostgreSQL and survives backend restarts. Jobs still pending/running when the backend stops are marked `failed` ("Interrupted by backend restart") on the next start; this assumes a single backend process.
- Video job results store every frame's detections in one JSONB value, so long videos produce very large rows.
- The desktop app defaults to `http://127.0.0.1:8000`, but this is now changeable per-machine in Settings if something else on your machine already uses that port (for example another Docker project) — see Backend connection in Settings.
- A packaged (built) desktop app cannot reach the backend yet: production Tauri pages load from `http://tauri.localhost`, but the backend's CORS only allows `http://localhost:1420` (the dev server origin). This only affects `npm run tauri build` output, not `npm run tauri dev`.
- No auth.
- The desktop build does not package or auto-start the backend/ai-engine/PostgreSQL — those must be running alongside the app.
- Camera connection status is only refreshed on demand (Test connection), not monitored continuously in the background — the badge can go stale if a camera drops between tests.
- A camera whose native OpenCV/FFmpeg connection attempt ignores its own timeout can still tie up one backend worker thread longer than the configured ~5s timeout (mitigated, not eliminated, by an outer hard timeout in `app/camera_testing.py`).
- Camera credentials travel over plain HTTP between desktop and backend — fine for same-machine loopback (today's only deployment shape), but will need TLS for the Vero Cloud plan.
- `location_label` on a camera is free text, not a real relationship to an Organization/Location — those don't exist until Phase 10.
- Tracking runs entirely on CPU (measured ~0.09s/frame on a 4-core i3 — no GPU code path exists). Each active tracking session uses roughly one full CPU core at the ~5fps target rate; several cameras tracked at once will contend with each other and with the backend's own request handling.
- A tracking session's `YOLO` model is loaded fresh on every Start (a one-off ~6-7s warm-up); starting/stopping the same camera repeatedly re-pays that cost each time.
- Restarting the backend silently stops all active tracking sessions (no persistence, no auto-resume) — the same on-demand-only philosophy as camera connection status.
- A dropped stream retries for about a minute (backoff, bounded attempts) before giving up and marking the session `error`; it does not retry forever, and it does not auto-restart on its own afterward.
- Entry/exit line counts are ephemeral, per tracking session — they reset to zero every time tracking starts. Historical/persistent analytics (today's total, trends over time) is Phase 9's job.
- Lines cannot be edited after creation (no drag-to-adjust, no reposition) — delete and redraw instead. Straight lines only, no zones/polygons.
- A camera's lines are deleted automatically if the camera itself is deleted (database cascade).
