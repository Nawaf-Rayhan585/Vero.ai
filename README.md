# Vero.ai

Desktop app for running YOLO-based object detection/segmentation/pose estimation on images and videos.

This is a working prototype, not the V1 product. See [docs/PROJECT.md](docs/PROJECT.md) for the product spec and [docs/ROADMAP.md](docs/ROADMAP.md) for the official phase-by-phase roadmap.

## Architecture

- **backend/** — FastAPI server. Users, organizations, memberships, locations, subscriptions, devices, refresh tokens, jobs, cameras (including which AI modules each one runs), entry/exit lines, custom zones, events and hourly heat snapshots are stored in PostgreSQL (SQLAlchemy + Alembic migrations); exposes `/auth/*`, `/organizations`, `/locations`, `/members`, `/subscription`, `/devices`, `/jobs`, `/cameras`, `/cameras/{id}/lines`, `/cameras/{id}/zones`, `/events` and `/analytics/*` endpoints. Every endpoint except `/health*` and `/auth/{register,login,refresh}` requires a signed-in user and is scoped to one organization (`app/auth.py`; JWT access tokens + rotating hashed refresh tokens, Argon2id password hashing in `app/security.py`). Every organization gets a 3-day trial on creation; configure actions that *grow* usage (add/edit a camera, line, zone, location, member, or device; start tracking) additionally need an active subscription (`require_active_configurator`, 402 once the trial's ended) — deleting, stopping tracking, and all reads are never blocked by billing status. An Owner-only manual override (`PATCH /subscription`) can also activate, expire or extend one directly — an admin/support fallback that coexists with real PayPal billing (Phase 15, below), not replaced by it. A `Device` is Own Hardware plan "device entitlement" (`PROJECT.md`) — just a name someone types (e.g. "Warehouse PC"), not a hardware fingerprint; nothing checks a request actually comes from a registered device. Camera passwords are encrypted at rest (`app/crypto.py`, Fernet); RTSP connectivity testing and snapshot grabbing (`app/camera_testing.py`) use OpenCV with a bounded timeout. Continuous person detection + tracking (`app/tracking.py`, Ultralytics YOLO + ByteTrack) runs one background thread per actively-tracked camera; entry/exit line-crossing counting (`app/counting.py`, pure geometry), zone occupancy (`app/zones.py`, point-in-polygon), and a per-session heatmap of where people stand (`app/heatmap.py`, numpy/OpenCV) all run inside that same loop. The same YOLO model also detects vehicles (car, motorcycle, bus, truck), counted at the same lines separately from people; QR codes and barcodes are decoded inline on each frame (`app/scanning.py`, zxing-cpp), and on-screen text is read by OCR (RapidOCR — PaddleOCR’s models via ONNX Runtime) on its own background thread so tracking never waits for it. Which of these run is a per-camera choice (`app/modules.py`); a camera with only QR/barcode/OCR enabled doesn’t even load YOLO. A session's live state — frame count, active tracks, in/out counts, zone occupancy, the heat grid, what the reading modules have read — stays in memory and resets every time tracking starts; but what it produces is written out by a background recorder (`app/events.py`) as structured events (line crossings, zone entered/left, reads, camera uptime) and hourly heat snapshots, and history is computed from those on demand (`app/analytics.py`). **Phase 13:** an organization whose `Subscription.plan_type` is `"vero_cloud"` has its camera tracking/testing/snapshot requests transparently forwarded to a separate `cloud-engine` service (`app/cloud_routing.py`) instead of running in this process — every other organization's requests are unaffected, byte-for-byte the same code path as before. **Phase 15:** real PayPal billing for the Own Hardware plan only (sandbox — Vero Cloud billing doesn't exist yet). `app/paypal_client.py` wraps PayPal's REST API directly (no SDK); `/subscription/paypal/checkout` creates a real subscription and returns its approval URL, `/subscription/paypal/sync` re-checks PayPal's status (the phase's actual verified mechanism — PayPal's real servers can't reach this loopback-only backend for webhooks), `/subscription/paypal/cancel` cancels immediately, and `/subscription/paypal/webhook` is real, signature-verified code that's untestable live in this environment. `backend/scripts/setup_paypal_plan.py` is a one-time script that creates the sandbox billing plan.
- **ai-engine/** — YOLO detection pipeline (`Detector` class). Imported directly by `backend/` (not a separate service).
- **cloud-engine/** (Phase 13) — a second, separate FastAPI service for the Vero Cloud plan, only reached by `backend` itself (never the desktop app), authenticated with a shared internal secret rather than JWT. It imports `backend/app/tracking.py` and friends directly (the same `sys.path` trick `backend/app/detection_runner.py` already uses for `ai-engine/`) and shares `backend`'s own PostgreSQL database — there is no separate cloud database. See `docs/ROADMAP.md`'s Phase 13 entry for what it does and does not do (still direct-RTSP ingestion, no NAT traversal; single process, no horizontal scaling; not deployed anywhere real).
- **desktop/** — Tauri + React UI, structured for the full app: `src/app/routes.tsx` is the single source of truth for the sidebar and router, `src/api/` is the typed backend client (automatically attaches the session's Authorization/organization headers and retries once on a 401 after a silent refresh), `src/auth/` holds the session (access token in memory, refresh token in the Windows Credential Manager via a Tauri command), `src/pages/` holds one component per section (Dashboard, Detect, Settings, Login, Register, Account, Subscription), `src/hooks/` wraps the API in React Query, `src/settings/` persists user preferences (including the backend URL) to `localStorage`. Signed out, the app shows Sign in/Create account instead of the app shell. The TopBar shows a trial countdown ("Trial: N days left" / "Trial ended — Upgrade") linking to the Subscription page, which also lists the organization's registered Devices; controls that grow usage (Add camera/location/member/device, Edit/Rename, role changes) hide once the trial's ended, same as they already hide for a Member. The Subscription page's **Billing** section (Phase 15, Owner-only, Own Hardware plan only) starts a real PayPal subscription and opens its approval page in the system's default browser (`@tauri-apps/plugin-opener`), not an embedded PayPal button. Talks to the backend over HTTP at `http://127.0.0.1:8000` by default — overridable per-machine from the in-app Settings page (Backend connection).

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
# Edit .env: set a real POSTGRES_PASSWORD (and matching DATABASE_URL), a real
# CAMERA_CREDENTIALS_KEY — generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# — and a real AUTH_SECRET_KEY (32+ characters) — generate one with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
# .env is gitignored. Losing/changing CAMERA_CREDENTIALS_KEY makes stored camera
# passwords unrecoverable; losing/changing AUTH_SECRET_KEY signs everyone out (all
# existing access/refresh tokens stop validating).
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

Once both are running, the app shows **Sign in**; click **Create one** the first time to register — this creates your account, your organization (you're its Owner), a default location, a 3-day trial subscription, and (only for the very first account ever registered) adopts any cameras/jobs already in the database into that organization. Add more people to your organization from **Account** once they've registered their own account (there is no invitation email yet). Once the trial ends, adding/editing things is blocked (402) until you activate the subscription — as Owner, on the **Subscription** page's manual override (there's no billing system yet, so this is the only way to activate one). The Subscription page also lets you register the machines you run Vero.ai on, under **Devices** — this is just a record you keep (a name you type), not something the app verifies against your actual hardware.

Click **Select Video/Image** in the app, choose a model and confidence threshold under **Settings**, then click **Run Detection**. Add a camera under **Cameras** (an RTSP URL, or a local video file path for testing without real camera hardware) and use **Test connection**; **Live View** shows a refreshing snapshot from the selected camera. Under **AI Modules**, click **Lines** to draw an entry/exit line (click two points directly on the camera image, name it, save), then click **Start tracking** to run continuous person detection + tracking + line counting — while it's running, Live View for that camera automatically switches to the AI-annotated feed, with lines and live in/out counts burned into the video itself. Click **Zones** to outline a custom zone (click 3 or more points on the image, **Finish zone**, name it, save) and the AI Modules page and the video then show a live count of people inside each zone. While tracking is running, tick **Show heatmap** in Live View to overlay where people have been standing since tracking started.

Each camera on the **AI Modules** page has an **AI modules** row of checkboxes — People (the default), Vehicles, Text (OCR), QR codes, Barcodes. It saves as soon as you tick, and takes effect the next time tracking starts on that camera. Vehicles are boxed in orange and counted at your lines next to the people counts; anything read (QR codes, barcodes, text) is boxed and labelled in magenta on the video and listed under **Recent reads**. Start tracking stays disabled until at least one module is ticked.

**Events** lists what your cameras observed, newest first and updating on its own (line crossings, zone activity, QR/barcode/text reads, and when tracking started, stopped or lost its camera), filterable by camera, kind and period. **Analytics** shows today, the last 7 days or the last 30 days for one camera or all of them: headline totals, a trend chart of in vs out per hour or day (hours where nothing was being tracked are hatched and labelled "not running", not drawn as zero traffic), a breakdown by line and by zone, and — for a chosen camera — a heatmap of where people stood. The **Dashboard** shows today's totals. All of it is kept after tracking stops.

The first detection run for a given model downloads its YOLO weights (e.g. `yolov8n.pt`) into `backend/` and caches them there for subsequent runs.

## Running the backend tests

PostgreSQL must be running. Tests use a separate `vero_test` database (created automatically) and never touch the dev database. They include real YOLO inference, so the first run takes a few seconds longer.

```powershell
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\backend"
.\venv\Scripts\Activate.ps1
python -m pytest -v
```

If PostgreSQL is not reachable the suite stops immediately with instructions — it never silently skips database tests.

## Running cloud-engine (Phase 13, optional)

Only needed to actually run the Vero Cloud plan locally, or to run `cloud-engine`'s own tests. It has no `venv` of its own — its `requirements.txt` is a subset of `backend`'s, so `backend`'s existing venv already has everything it needs.

```powershell
# One-time: set CLOUD_ENGINE_INTERNAL_SECRET and CLOUD_ENGINE_BASE_URL in .env (see .env.example)
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\cloud-engine"
..\backend\venv\Scripts\Activate.ps1
python -m uvicorn main:app --port 8002
```

```powershell
# Its own tests (PostgreSQL must be running; shares backend's vero_test database)
cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\cloud-engine"
..\backend\venv\Scripts\Activate.ps1
python -m pytest -v
```

## Setting up PayPal billing (Phase 15, optional)

Only needed to actually subscribe an organization via PayPal (Own Hardware plan only — Vero Cloud billing doesn't exist yet), or to exercise it against PayPal's real sandbox rather than the mocked test suite. Free: a sandbox app needs no real business account or payment method.

1. Create a free app at [developer.paypal.com/dashboard/applications](https://developer.paypal.com/dashboard/applications) and copy its sandbox Client ID/Secret into `.env` as `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`. Set `PAYPAL_RETURN_BASE_URL` too (see `.env.example`).
2. Run the one-time setup script to create the Own Hardware billing plan (a placeholder $19.99/month — not a real, decided price):
   ```powershell
   cd "F:\AI Dev\Vero.ai SaaS Platform\vero.ai\backend"
   .\venv\Scripts\Activate.ps1
   python scripts\setup_paypal_plan.py
   ```
   Add the printed plan ID to `.env` as `PAYPAL_OWN_HARDWARE_PLAN_ID`.
3. Optional: add a webhook in the sandbox app's dashboard pointed at `{PAYPAL_RETURN_BASE_URL}/subscription/paypal/webhook`, and put its ID in `.env` as `PAYPAL_WEBHOOK_ID`. This only receives anything if that URL is actually publicly reachable (a plain `127.0.0.1` dev setup isn't) — the app works without it via the Subscription page's "Check status" button instead.

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
- Auth is JWT access tokens (~15 min default) plus rotating refresh tokens; there is no email service, so no email verification, no password reset (only an in-app change-password while signed in), and adding someone to an organization requires they already have an account. No rate limiting/lockout on login yet. Being added to an organization isn't pushed to an already-open session — sign out/in (or wait for the next silent token refresh) to see it.
- Every organization gets a 3-day trial; once it ends, growing usage (add/edit a camera/line/zone/location/member/device, start tracking) is blocked until it's reactivated. Own Hardware can now be reactivated via a real (sandbox) PayPal subscription (Phase 15, the Subscription page's Billing section) or, still, the Owner-only manual override — plan type (Own Hardware / Vero Cloud) is chosen there too. Vero Cloud has no billing yet (its real price is still a pending business decision, `docs/PRICING-MODEL.md`), but switching to it does change behavior: that organization's camera tracking/testing/snapshot requests run on a separate `cloud-engine` service instead of locally (see above). There are still no real entitlement limits on either plan (camera-count and device-count limiting exist as tested code but nothing sets a number).
- Device entitlement (Subscription page) is a soft record, not real hardware-binding: an Owner/Admin types a device name, and nothing checks that traffic actually comes from a registered machine, or restricts device registration to any particular plan.
- PayPal billing (Phase 15) is sandbox-only — no real business account, no real money, never goes live without an explicit later decision. It's Own Hardware only; canceling and re-subscribing is the only way to change anything about an existing subscription (no in-place upgrade/downgrade). Real inbound webhook delivery is untested: PayPal's real servers can't reach this dev environment's loopback-only backend, so the Subscription page's "Check status" button (an outbound call to PayPal) is what actually keeps a subscription's status current here, not the webhook.
- The desktop build does not package or auto-start the backend/ai-engine/PostgreSQL — those must be running alongside the app.
- Camera connection status is only refreshed on demand (Test connection), not monitored continuously in the background — the badge can go stale if a camera drops between tests.
- A camera whose native OpenCV/FFmpeg connection attempt ignores its own timeout can still tie up one backend worker thread longer than the configured ~5s timeout (mitigated, not eliminated, by an outer hard timeout in `app/camera_testing.py`).
- Camera credentials travel over plain HTTP between desktop and backend — fine for same-machine loopback (today's only deployment shape), but will need TLS for the Vero Cloud plan.
- Accounts and organizations live in this same local backend/PostgreSQL, not a separate cloud service, for both plans — `docs/ARCHITECTURE.md`'s target puts Auth in "Vero.ai Cloud", but Phase 13's scope was camera-processing routing only (see above); whether/when accounts move to their own service is still an open decision.
- Tracking runs entirely on CPU (measured ~0.09s/frame on a 4-core i3 — no GPU code path exists). Each active tracking session uses roughly one full CPU core at the ~5fps target rate; several cameras tracked at once will contend with each other and with the backend's own request handling.
- A tracking session's `YOLO` model is loaded fresh on every Start (a one-off ~6-7s warm-up); starting/stopping the same camera repeatedly re-pays that cost each time.
- Restarting the backend silently stops all active tracking sessions (no persistence, no auto-resume) — the same on-demand-only philosophy as camera connection status.
- A dropped stream retries for about a minute (backoff, bounded attempts) before giving up and marking the session `error`; it does not retry forever, and it does not auto-restart on its own afterward.
- The live entry/exit counters (AI Modules page, Live View) are per tracking session and reset every time tracking starts; the history is in Events and Analytics, which keep every crossing.
- Lines cannot be edited after creation (no drag-to-adjust, no reposition) — delete and redraw instead. Straight lines only, no zones/polygons.
- A camera's lines and zones are deleted automatically if the camera itself is deleted (database cascade).
- Zones cannot be edited after creation — delete and redraw. A zone's live count is who is inside it right now (judged by the position of their feet); there are no timers. Zone visits (entered / left) are recorded as events and shown on Analytics.
- The live heatmap starts empty every time tracking starts, and a person standing still builds heat faster than one walking through. Heat is also saved hourly, and Analytics can show a past period; it is drawn over a fresh camera snapshot when the camera answers, or on a plain background when it does not.
- OCR is CPU-heavy: on the dev machine a pass takes roughly 1 s and, while it runs, YOLO’s per-frame time about doubles. It runs on a background thread at most every 5 seconds, reads the whole frame (no region selection), and its cadence has not been tuned or tested with several cameras at once.
- QR codes and barcodes are only read if they take up enough of the frame: about 200 px wide in a 720p image worked, about 120 px did not, and tilted 1D barcodes are not read. OCR was verified on rendered text and one real photograph, not on real CCTV footage.
- Reads (QR/barcode/text) are deduplicated per session and kept in memory only — the 50 most recent, each with a sighting count. Vehicles are counted, not broken down by type, and the detector occasionally mislabels (a person as a bus for one frame was seen in test footage). Zones and the heatmap are people-only.
- The reading modules add RapidOCR, ONNX Runtime and zxing-cpp (11 pinned packages in `backend/requirements.txt`); the OCR models ship inside the package, so nothing downloads at runtime. That is roughly 40 MB more for the eventual installer to ship.
- Events are kept forever (no retention setting or purge yet), and deleting a camera deletes its events and heat history along with it. Delivery is at-most-once: a hard crash can lose about the last second of events.
- A zone visit counts again if someone is hidden for more than about five seconds and then reappears, and the tracker's occasional ID switches can inflate crossings and visits slightly.
- Analytics charts are cut in your computer's time zone; the repeated hour on the day the clocks go back merges into one bucket. Times of "tracked" are camera time (two cameras for an hour is two hours).
