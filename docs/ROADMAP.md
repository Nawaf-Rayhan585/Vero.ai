# Vero.ai — Roadmap

**This is the official roadmap.** It supersedes any prior phase list or roadmap draft produced before this specification was recorded.

## Phases

| Phase | Scope |
|---|---|
| 0 | Product definition, architecture, scope, development rules *(this documentation)* |
| 1 | Clean project foundation and scaffolding |
| 2 | FastAPI + PostgreSQL backend foundation |
| 3 | Desktop application architecture and dashboard foundation |
| 4 | CCTV/RTSP camera manager |
| 5 | AI detection + tracking engine |
| 6 | People counting + entry/exit analytics |
| 7 | Zones + heatmaps |
| 8 | Vehicle detection/counting + OCR + QR + barcode |
| 9 | Events + analytics system |
| 10 | Authentication + organizations + locations |
| 11 | 3-day trial + subscription/licensing architecture |
| 12 | Own Hardware plan implementation |
| 13 | Vero Cloud infrastructure |
| 14 | Cloud cost/unit economics + pricing model |
| 15 | PayPal subscription integration |
| 16 | Production packaging + automatic service management |
| 17 | Security + performance hardening |
| 18 | Full testing |
| 19 | Private beta |
| 20 | Vero.ai V1 launch |

Future V2 features (dwell time, queue detection, PPE, fire/smoke, license plate recognition, etc. — full list in [V1-SCOPE.md](V1-SCOPE.md)) are not part of this roadmap unless explicitly moved into it later.

## Current status

**Phases 0-6 are accepted by the owner.** **Phase 7 (zones + heatmaps) is implemented and awaiting owner verification** — it is not marked complete until the owner has verified it (Development Rule 6). Phase 8 has not started.

### What exists today

- `backend/` — FastAPI + SQLAlchemy 2 (sync) + Alembic + PostgreSQL 16. Layout: `main.py` and `app/` (`config`, `database`, `models`, `schemas`, `crypto`, `detection_runner`, `camera_testing`, `tracking`, `counting`, `zones`, `heatmap`, `routers/jobs`, `routers/cameras`, `routers/tracking`, `routers/lines`, `routers/zones`). Endpoints: `GET /health`, `GET /health/db`, `POST/GET /jobs`, `GET /jobs/{id}`, full `/cameras` CRUD, `POST /cameras/{id}/test-connection`, `GET /cameras/{id}/snapshot`, `/cameras/{id}/tracking/{start,stop,status,latest-frame}` (`latest-frame?heatmap=true` returns the same annotated frame with the accumulated heat blended on), `/cameras/{id}/lines` (create/list) + `DELETE /lines/{id}`, and `/cameras/{id}/zones` (create/list) + `DELETE /zones/{id}`. Four tables (`jobs`, `cameras`, `lines`, `zones`) and four migrations — `lines` and `zones` cascade on camera delete; a zone's polygon is a JSONB list of normalized points. Tracking sessions (live in/out counts, live zone occupancy, the heat grid) are **not** a table; fully in-memory, one background thread per actively-tracked camera, reset every time tracking starts. Camera passwords are encrypted at rest and never returned by the API. 158 automated tests (pytest, real PostgreSQL, real YOLO/ByteTrack inference, real OpenCV) live in `backend/tests/`.
- Local PostgreSQL runs via `docker-compose.yml` (development only) on `127.0.0.1:5433`.
- `ai-engine/` — unchanged from the prototype; tracking, counting, zones, and heatmaps live in `backend/app/` instead (see Phase 5's entry).
- `desktop/` — Tauri v2 + React 19 + TypeScript app shell. Pages: Dashboard, Detect, Settings, Cameras, **AI Modules** (per-camera Start/Stop tracking, live status + track count + per-line in/out counts, and a **Lines** toggle opening `components/LineEditor.tsx` — click two points directly on the camera's frame to place an entry/exit line, name it, save; existing lines listed with delete), a **Zones** toggle opening `components/ZoneEditor.tsx` (click 3+ points on the camera's frame, undo, finish, name, save; existing zones listed with delete) and a live "N inside" count per zone, **Live View** (the AI-annotated feed also shows each line with its live count and each zone with its live occupancy burned into the video, drawn server-side; while tracking is active a **Show heatmap** checkbox swaps the feed to the same frame with the accumulated heat overlay). Events, Analytics, Account, and Subscription remain honest placeholders naming the phase that builds them. 88 automated tests (Vitest + Testing Library, API layer mocked, no backend required) live alongside the source files they test.
- Repo-root `shared/` and `tests/` are still empty placeholders (backend tests live in `backend/tests/`, desktop tests live in `desktop/src/`).
- Still not implemented: vehicle analytics, OCR/QR/barcode, events/persistent analytics (today's totals, trends), authentication, organizations, locations, trial, licensing, subscription, PayPal, cloud infrastructure, production backend orchestration, a self-contained installer, continuous/background camera connection monitoring, and any User/Organization/Location/Event tables.
- The Windows installer (`tauri build` → MSI/NSIS) still cannot run standalone on a clean PC: the backend (`uvicorn`) and PostgreSQL must both be started separately, and a packaged build additionally can't reach the backend at all yet (see Open items).

### Resolved since Phase 0

- Phase 1: `README.md` paths and product name updated; stray `ai-engine/job1.json` removed; `backend/requirements.txt` re-encoded from UTF-16 to UTF-8.
- Phase 2: `README.md` and `start-dev.ps1` updated for the PostgreSQL dependency.
- Phase 3: the port-8000-clash open item from Phase 2 is resolved — the backend URL is now a Settings-page override, not a hardcoded constant.
- Phase 4: none of the prior open items were in scope for this phase; two new bugs were found and fixed *during* this phase (not carried forward) — see the Phase 4 entry below.
- Phase 5: none of the prior open items were in scope; one more real bug found and fixed *during* this phase (also below), plus one missing dependency (`ultralytics`'s tracker needs `lap`, whose own auto-installer failed silently — installed manually and verified before writing any tracking code).
- Phase 6: none of the prior open items were in scope. Two test-writing mistakes were caught and fixed during this phase (not application bugs, but worth knowing about if extending these tests) — see below.
- Phase 7: none of the prior open items were in scope. One heatmap rounding bug was caught while writing the tests and fixed before it shipped, plus a live-check tooling pitfall — see below.

### Bugs found and fixed during Phase 4 (worth knowing about)

- **OpenCV/FFmpeg silently ignored its own connect/read timeouts** when set via `cv2.VideoCapture()` + `.set(...)` + `.open(...)`, falling back to an internal ~30s default regardless of the requested value. Fixed by using the `cv2.VideoCapture(url, backend, [prop, value, ...])` constructor form instead, which does honor it (confirmed empirically). Also fixed a related bug where the outer "hard timeout" safety net used a `with ThreadPoolExecutor(...):` block, whose `__exit__` blocked on `shutdown(wait=True)` and defeated the timeout entirely by waiting for the abandoned thread anyway.
- **A raw `<img src="…snapshot">` never shows a broken camera's real error.** Chromium's Opaque Response Blocking silently drops a non-image (JSON error) body on a cross-origin no-cors image request — the `<img>` element's `onerror` never fires, so the UI would show nothing at all, indefinitely, for an unreachable camera. Confirmed live against a genuinely unreachable address before switching Live View to fetch the snapshot via `fetch()` (a normal CORS-mode request) and rendering it through an object URL instead.

### Bugs found and fixed during Phase 5 (worth knowing about)

- **A background thread's `finally: cap.release()` could crash on `None`.** When the reconnect loop gave up (or was interrupted by `stop()`), `cap` became `None`, and the unconditional `cap.release()` in `TrackingSession._run()`'s `finally` block would raise `AttributeError` in the background thread. Caught before it ever ran, by tracing the give-up/stop paths by hand; fixed with a `None` guard.
- **`status: "running"` doesn't mean a frame has been processed yet.** The tracking loop sets status to `running` as soon as the camera connection opens, but the *first* `model.track()` call pays a one-off ~6-7s warm-up cost (confirmed by direct measurement) before any frame/track data exists. This is real, expected behavior, not a bug — but it did catch out an early version of the AI Modules row logic, and is worth knowing if `frame_count`/`active_track_ids` look like 0 right after starting.

### Testing pitfalls found and fixed during Phase 6 (not application bugs)

- A naive "paste a person crop onto a plain background" synthetic test video produced **zero** YOLO detections — confirmed empirically before relying on it. The working technique instead pans a cropped window across the real `bus.jpg` photo (every pixel stays genuinely real, only what's visible shifts), which reliably produces stable track IDs with monotonically-shifting positions — a real, honest way to test line-crossing end to end without a physical camera.
- The test DB truncation helper (`clean_tables` in `tests/conftest.py`) had to be updated to include the new `lines` table — Postgres refuses to truncate `cameras` alone once another table has a foreign key into it. Anyone adding a new table with a FK to an existing one needs to remember this.

### Found and fixed during Phase 7 (worth knowing about)

- **Heatmap rendering truncated instead of rounding.** The blend ended in `.astype(np.uint8)`, which truncates: a pixel nobody walked near (alpha ~ 0) could come out one level darker than the original whenever float error landed just under its value. Caught while writing the "distant pixel is left exactly alone" test, before running it; fixed with `np.rint(...)` in `app/heatmap.py`.
- **Testing pitfall (tooling, not the app): Playwright cannot read the body of a `fetch()`-made response through a `page.on("response")` listener.** The live check's attempt to save the raw JPEGs the backend served produced zero-byte files. The verification relies on the browser screenshots of Live View instead, which show exactly what the app renders. If raw served frames are ever needed, fetch them with `page.request` rather than sniffing the page's own responses.
- The `panning_video` test fixture moved from `tests/test_tracking_counting.py` into `tests/conftest.py` so the zone/heatmap end-to-end test could share it; `clean_tables` gained `zones` (the same foreign-key lesson as Phase 6).

### Open items needing an owner decision

- **PostgreSQL for the Own Hardware plan.** The spec mandates PostgreSQL project-wide and that end users never run Python/Uvicorn manually. Phases 12 and 16 must decide how a customer's machine gets PostgreSQL (a managed local instance installed and supervised by the installer, or the local engine syncing to a cloud PostgreSQL only). Not decided in Phase 2.
- **Packaged app can't reach the backend.** A production Tauri build loads from `http://tauri.localhost`, but the backend's CORS only allows `http://localhost:1420` (the dev server origin). Only affects `npm run tauri build` output, not `npm run tauri dev`. Belongs to Phase 16/17.
- Video job results are stored as one JSONB value per job; a redesign belongs to Phase 9.
- **Camera `location_label` is free text, not a relationship.** Phase 10 will need a migration to reconcile it with real `Location` rows once those exist.
- **No physical RTSP camera was tested** (Phases 4-6). All connectivity/snapshot/tracking/counting testing used a genuinely unreachable address (fast-fail path) and synthetic local video files standing in for a readable/moving stream (success path) — OpenCV's open/read logic doesn't distinguish file paths from RTSP URLs internally, so this exercises the real code path, but real-camera specifics (auth negotiation, codecs, vendor quirks, sustained real-world network drops, real pedestrian behavior) are unverified.
- **CPU-only tracking, no admission control.** Confirmed ~0.09s/frame on this dev machine's 4-core CPU (no GPU available to test against); the code doesn't limit how many cameras can be tracked concurrently, so heavy concurrent use is untested.
- **Entry/exit counts are ephemeral, per session.** No historical/persistent analytics yet (today's total, trends over time) — that's Phase 9's explicit job. Restarting tracking or the backend resets all counts to zero.
- **Lines cannot be edited after creation.** No drag-to-adjust or reposition — delete and redraw is the only way to change one. A deliberate scope cut for this phase, not a bug.
- **Zones cannot be edited after creation either** — delete and redraw, same deliberate scope cut as lines.
- **Zone counts and the heatmap are ephemeral, per session.** A zone reports only who is inside it *right now* — no timers (dwell time is V2), no entry totals, no history — and the heat grid starts empty on every Start. There is no reset-while-running control; stop and start again. Persistent/historical versions belong to Phase 9.
- **Zone edge cases were left permissive on purpose.** A person counts as inside by the position of their feet (bottom-center of the box), a point exactly on an edge counts as inside, self-intersecting ("bow-tie") polygons are accepted and follow the even-odd rule, and a zero-area polygon is accepted and simply always reads 0. Say if you'd rather have these rejected at creation.
- **The heatmap measures presence over the whole session, so a person standing still builds heat faster than one walking through.** That is normal heatmap behavior, but it is also why it looks smeared along paths. The heat overlay is rendered by the backend on request (one extra JPEG encode per Live View refresh while the toggle is on), not pre-rendered.
- **Heatmap usefulness on real footage is unverified.** The accumulation and blending are tested, and the live check shows heat trailing real detected people's feet on synthetic panning footage, but how it reads over a busy day of real traffic on a real camera has not been seen.

## Next step

Owner verification of Phase 7, then the explicit instruction **"START PHASE 8"**.
