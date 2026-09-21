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

**Phases 0-8 are accepted by the owner.** **Phase 9 (events + analytics system) is implemented and awaiting owner verification** — it is not marked complete until the owner has verified it (Development Rule 6). Phase 10 has not started.

### What exists today

- `backend/` — FastAPI + SQLAlchemy 2 (sync) + Alembic + PostgreSQL 16. Layout: `main.py` and `app/` (`config`, `database`, `models`, `schemas`, `crypto`, `detection_runner`, `camera_testing`, `tracking`, `counting`, `zones`, `heatmap`, `modules`, `scanning`, `events`, `analytics`, `routers/jobs`, `routers/cameras`, `routers/tracking`, `routers/lines`, `routers/zones`, `routers/events`, `routers/analytics`). Endpoints: `GET /health`, `GET /health/db`, `POST/GET /jobs`, `GET /jobs/{id}`, full `/cameras` CRUD, `POST /cameras/{id}/test-connection`, `GET /cameras/{id}/snapshot`, `/cameras/{id}/tracking/{start,stop,status,latest-frame}` (`latest-frame?heatmap=true` returns the same annotated frame with the accumulated heat blended on), `/cameras/{id}/lines` (create/list) + `DELETE /lines/{id}`, `/cameras/{id}/zones` (create/list) + `DELETE /zones/{id}`, `GET /events` (filterable by camera/type/category/time, newest first, cursor-paged), and `GET /analytics/{summary,timeseries,heatmap/info,heatmap}` (totals, zero-filled hourly/daily buckets in any IANA time zone with the time tracking actually ran, and saved heatmaps). Six tables (`jobs`, `cameras`, `lines`, `zones`, `events`, `heatmap_snapshots`) and six migrations (the latest creates `events` and `heatmap_snapshots`) — `lines`, `zones`, `events` and `heatmap_snapshots` cascade on camera delete (deleting a camera deletes its history); a zone's polygon is a JSONB list of normalized points. A tracking session's live state (in/out counts for people and vehicles, zone occupancy, the heat grid, what the QR/barcode/OCR modules have read) is still in memory — one background thread per actively-tracked camera, reset every time tracking starts — but everything it produces is now also written out by an in-process recorder as structured events (line crossings, zone entered/left, reads, camera uptime) and hourly heat snapshots, so it survives stopping tracking and restarting the backend. Camera passwords are encrypted at rest and never returned by the API. 425 automated tests (pytest, real PostgreSQL, real YOLO/ByteTrack inference, real OpenCV) live in `backend/tests/`.
- Local PostgreSQL runs via `docker-compose.yml` (development only) on `127.0.0.1:5433`.
- `ai-engine/` — unchanged from the prototype; tracking, counting, zones, and heatmaps live in `backend/app/` instead (see Phase 5's entry).
- `desktop/` — Tauri v2 + React 19 + TypeScript app shell. Pages: Dashboard, Detect, Settings, Cameras, **AI Modules** (a per-camera **module selector** — People, Vehicles, Text (OCR), QR codes, Barcodes — saved on the camera and applied the next time tracking starts; Start/Stop tracking, live status + person and vehicle track counts + per-line in/out counts (people, plus vehicles when Vehicles is on), a **Recent reads** list of the QR codes/barcodes/text seen this session, and a **Lines** toggle opening `components/LineEditor.tsx` — click two points directly on the camera's frame to place an entry/exit line, name it, save; existing lines listed with delete), a **Zones** toggle opening `components/ZoneEditor.tsx` (click 3+ points on the camera's frame, undo, finish, name, save; existing zones listed with delete) and a live "N inside" count per zone, **Live View** (the AI-annotated feed also shows each line with its live count and each zone with its live occupancy burned into the video, drawn server-side; while tracking is active a **Show heatmap** checkbox swaps the feed to the same frame with the accumulated heat overlay). **Events** (newest-first list of what the cameras observed, as sentences, filterable by camera, kind and period, with Load more and automatic refresh) and **Analytics** (today / 7 / 30 days for one camera or all: headline tiles, a hand-drawn SVG trend chart of in vs out per hour or day where hours with no tracked time are hatched and labelled "not running" rather than drawn as zero traffic, by-line and by-zone tables, and a saved-heatmap view) are real pages now, and the Dashboard has a **Today** row of tiles. Account and Subscription remain honest placeholders naming the phase that builds them. 205 automated tests (Vitest + Testing Library, API layer mocked, no backend required) live alongside the source files they test.
- Repo-root `shared/` and `tests/` are still empty placeholders (backend tests live in `backend/tests/`, desktop tests live in `desktop/src/`).
- Still not implemented: license-plate recognition and parking analytics (V2), authentication, organizations, locations, trial, licensing, subscription, PayPal, cloud infrastructure, production backend orchestration, a self-contained installer, continuous/background camera connection monitoring, and any User/Organization/Location tables.
- The Windows installer (`tauri build` → MSI/NSIS) still cannot run standalone on a clean PC: the backend (`uvicorn`) and PostgreSQL must both be started separately, and a packaged build additionally can't reach the backend at all yet (see Open items).

### Resolved since Phase 0

- Phase 1: `README.md` paths and product name updated; stray `ai-engine/job1.json` removed; `backend/requirements.txt` re-encoded from UTF-16 to UTF-8.
- Phase 2: `README.md` and `start-dev.ps1` updated for the PostgreSQL dependency.
- Phase 3: the port-8000-clash open item from Phase 2 is resolved — the backend URL is now a Settings-page override, not a hardcoded constant.
- Phase 4: none of the prior open items were in scope for this phase; two new bugs were found and fixed *during* this phase (not carried forward) — see the Phase 4 entry below.
- Phase 5: none of the prior open items were in scope; one more real bug found and fixed *during* this phase (also below), plus one missing dependency (`ultralytics`'s tracker needs `lap`, whose own auto-installer failed silently — installed manually and verified before writing any tracking code).
- Phase 6: none of the prior open items were in scope. Two test-writing mistakes were caught and fixed during this phase (not application bugs, but worth knowing about if extending these tests) — see below.
- Phase 7: none of the prior open items were in scope. One heatmap rounding bug was caught while writing the tests and fixed before it shipped, plus a live-check tooling pitfall — see below.
- Phase 8: none of the prior open items were in scope. One real UI bug was found by the live browser check (not by the unit tests) and fixed, plus a few testing pitfalls — see below.
- Phase 9: resolves the "ephemeral, no history" items carried since Phases 6-8 (line counts, zone activity, heat and reads are now stored as events / hourly snapshots and shown historically). The Detect-page job-results redesign that was pointed at this phase was deferred by the owner's choice (still open, below). Three real bugs were found and fixed (two by the tests, one by the live check) — see below.

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

### Found and fixed during Phase 8 (worth knowing about)

- **A module checkbox could fail to visibly change at the moment of the click.** Found by the live browser check, not by the unit tests: the box’s "just clicked" state came from the save’s pending state, which React Query updates a tick after the click, and a controlled checkbox snaps back to its old value in between (Playwright reported that clicking the checkbox did not change its state). Fixed by holding the click in local state until the save settles (`components/ModuleSelector.tsx`), with a regression test asserting the box is already checked in the same tick as the click — confirmed failing on the old code first.
- **Testing pitfalls (not app bugs).** Never `from tests.conftest import ...`: that re-executes conftest under a second module name, and its top-level code rewrites `DATABASE_URL` (which would point the tests at `<db>_test_test`) — share values through fixtures instead. zxing-cpp’s `|` operator on `BarcodeFormat` is deprecated; pass a list of formats.
- **A wrong claim in my own planning, caught before it reached the docs:** I thought the OCR model garbled accented letters; that was my terminal’s encoding, and the model reads "eléctricamEMTe" correctly.
- Three existing tests that pinned exact response shapes (the camera keys; two line-count dicts) were updated for the new additive fields (`enabled_modules`, `vehicle_in_count`/`vehicle_out_count`). Nothing else in the Phase 1-7 tests changed behavior.
- Docker Desktop was down again at the start of this phase (the known quirk) and had to be relaunched.

### Found and fixed during Phase 9 (worth knowing about)

- **A phantom hour on the clocks-forward day.** Cutting hourly buckets in PostgreSQL produced a zero-length 02:00 bucket for the local hour that doesn't exist on the day the clocks go forward (24 buckets for a 23-hour day), which a chart would have shown as a spurious "not running" sliver. Caught by a test of New York's 2026 spring-forward day; fixed by skipping zero-length buckets. (The opposite case, the repeated hour on the clocks-back day, merges into one bucket, and is documented below.)
- **Switching camera on Analytics showed the previous camera's totals, undimmed, until the new numbers arrived.** Found by the live browser check (after selecting the Dock camera the tiles still read the Street camera's figures). The chart already dimmed its previous render while loading, but the tiles and breakdown tables did not, so old numbers looked current. Fixed: tiles and tables are dimmed too, and the "nothing was tracked" note is withheld while the numbers are stale; covered by a test.
- **Closing a dangling session was ambiguous and not repeatable.** The startup step that closes a session a crash left "running" stamped its closing event at exactly the last event's time, so the two tied, "the latest uptime event" was ambiguous, and running the step twice closed the session twice. Caught by tests; fixed by stamping it one microsecond later.
- Smaller things found and fixed while testing: a bad (non-database) item in the write queue would have been retried forever and blocked everything behind it — it is now isolated and dropped; a test's dates accidentally straddled the US clock change (test data, not the code).
- **Testing pitfalls (tooling):** the Bash tool fails on long heredocs containing backticks, so multi-line edits were done with patch scripts instead; and the status badges are styled uppercase, so a browser script reading a page's `innerText` sees "TRACKING STARTED" and needs a case-insensitive match.

### Open items needing an owner decision

- **PostgreSQL for the Own Hardware plan.** The spec mandates PostgreSQL project-wide and that end users never run Python/Uvicorn manually. Phases 12 and 16 must decide how a customer's machine gets PostgreSQL (a managed local instance installed and supervised by the installer, or the local engine syncing to a cloud PostgreSQL only). Not decided in Phase 2.
- **Packaged app can't reach the backend.** A production Tauri build loads from `http://tauri.localhost`, but the backend's CORS only allows `http://localhost:1420` (the dev server origin). Only affects `npm run tauri build` output, not `npm run tauri dev`. Belongs to Phase 16/17.
- **Video job results are still one JSONB value per job** (the Detect prototype page). The roadmap had pointed this redesign at Phase 9; you chose to defer it, since Detect is the pre-V1 prototype and is not in V1's feature list. Revisit if the page survives to launch.
- **Camera `location_label` is free text, not a relationship.** Phase 10 will need a migration to reconcile it with real `Location` rows once those exist.
- **No physical RTSP camera was tested** (Phases 4-6). All connectivity/snapshot/tracking/counting testing used a genuinely unreachable address (fast-fail path) and synthetic local video files standing in for a readable/moving stream (success path) — OpenCV's open/read logic doesn't distinguish file paths from RTSP URLs internally, so this exercises the real code path, but real-camera specifics (auth negotiation, codecs, vendor quirks, sustained real-world network drops, real pedestrian behavior) are unverified.
- **CPU-only tracking, no admission control.** Confirmed ~0.09s/frame on this dev machine's 4-core CPU (no GPU available to test against); the code doesn't limit how many cameras can be tracked concurrently, so heavy concurrent use is untested.
- **The live counters still reset on every Start; the history lives in events.** The numbers on the AI Modules page and in Live View are per session, but everything counted is also stored as events, so today's totals and trends survive stopping tracking and restarting the backend.
- **Lines cannot be edited after creation.** No drag-to-adjust or reposition — delete and redraw is the only way to change one. A deliberate scope cut for this phase, not a bug.
- **Zones cannot be edited after creation either** — delete and redraw, same deliberate scope cut as lines.
- **A zone's live count is "who is inside right now" only** (no timers — dwell time is V2), and the live heatmap has no reset-while-running control (stop and start again). History is in the zone entered/left events and the saved hourly heat, both on the Analytics page.
- **Zone edge cases were left permissive on purpose.** A person counts as inside by the position of their feet (bottom-center of the box), a point exactly on an edge counts as inside, self-intersecting ("bow-tie") polygons are accepted and follow the even-odd rule, and a zero-area polygon is accepted and simply always reads 0. Say if you'd rather have these rejected at creation.
- **The heatmap measures presence over the whole session, so a person standing still builds heat faster than one walking through.** That is normal heatmap behavior, but it is also why it looks smeared along paths. The heat overlay is rendered by the backend on request (one extra JPEG encode per Live View refresh while the toggle is on), not pre-rendered.
- **Heatmap usefulness on real footage is unverified.** The accumulation and blending are tested, and the live check shows heat trailing real detected people's feet on synthetic panning footage, but how it reads over a busy day of real traffic on a real camera has not been seen.
- **OCR is CPU-heavy and reads the whole frame.** Measured on this dev machine: ~0.65-1.5 s per pass, and while a pass runs YOLO’s per-frame time roughly doubled (157 → 316 ms). Mitigations in place: OCR runs on its own background thread (tracking never waits for it), at most one pass every 5 s (`OCR_INTERVAL_SECONDS`), with ONNX threads capped at 2 (`OCR_THREADS`) — but those numbers are constants I chose, not tuned, and sustained multi-camera load with OCR on is untested. There is no way to limit OCR to a region or zone.
- **Code reading needs the code to be big enough in the frame.** With zxing-cpp, QR / Code 128 / EAN codes about 200 px wide in a 720p frame read; about 120 px did not, and 1D barcodes tilted ~20° were not read (a test pins that a ~60 px barcode is not decoded). Real CCTV placement is the risk; nothing here was tried on a real camera.
- **OCR accuracy on real signage is unverified** beyond the `bus.jpg` photo: English/Spanish Latin text read (“cero”, “emisiones” at 0.99-1.0) but “M1 SOL/SEVILLA” came out as “M15OL/SEUILLA” at 0.84. Other scripts/languages were not tested.
- **The live reads list is deduplicated per session.** A QR/barcode/text value is one entry with a sighting count (a new sighting only after a 5 s gap) and the 50 most recent are shown; each new sighting is also stored as a `read` event.
- **Vehicles: counted, not broken down, and misdetections happen.** Vehicles are car, motorcycle, bus and truck from the same YOLO model, counted at the same lines but separately from people; the box label shows the class, but counts are not split by type. In the real test footage a person was detected as a "bus" for a single frame — flicker like that can create a short-lived spurious vehicle track. Zones and the heatmap remain people-only.
- **Module changes apply on the next Start**, like lines and zones; a running session keeps what it started with (the UI says so).
- **11 new pinned packages:** RapidOCR 3.9.2 + ONNX Runtime 1.30.0 (CPU only, no GPU path) + zxing-cpp 3.1.1 and their small dependencies. RapidOCR’s PaddleOCR models are bundled in its wheel, so nothing downloads at runtime (offline-safe). This adds roughly 40 MB of models plus ONNX Runtime to what Phase 16’s installer will have to ship.
- **Deleting a camera deletes its events and heat history.** Consistent with its lines and zones, and the delete confirmation now says so, but it is a real loss of analytics. Say if you would rather history be kept (which needs a decision about what a camera-less event belongs to — likely a Phase 10 question once organizations and locations exist).
- **No retention or purge, and growth is unmeasured.** Every event is kept forever. Rows are small (a line crossing is one narrow row), and heat is about 1 KB per camera per hour, but how the table grows over months on a busy camera has not been observed, and the Phase 11/14 plans may want history limits.
- **Events are at-most-once.** They pass through a bounded in-memory queue: a hard crash can lose about the last second, a full queue drops the newest (counted), a database outage is retried but not forever, and an event whose camera was deleted mid-session is dropped. The writer never blocks or crashes tracking. After a crash, the startup step closes sessions at each camera's last event, so uptime is under- rather than over-stated.
- **Zone "entered" counts visits, and the tracker can inflate counts a little.** A person hidden for more than about five seconds and then reappearing counts as entering again (and an exit is recorded when they are lost), and an ID switch by the tracker can add a crossing or a visit. Real footage and real cameras have not been used to see how large this is.
- **Time-zone edge cases.** Charts are cut in the browser's IANA time zone (Postgres does the maths). The repeated hour on the clocks-back day merges into one bucket (24 buckets for a 25-hour day); the skipped hour on the clocks-forward day is not shown. Very long ranges are refused rather than truncated (more than 1,000 buckets).
- **"Tracked" is camera time.** For all cameras it is the sum of camera-seconds, so two cameras running for an hour show two hours, and an hour reads "not running" only if no camera was running in it.
- **The historical heatmap is hour-accurate at its edges and needs the camera to be reachable to sit on a real picture.** Snapshots are hourly, so the hour containing the start of the range is included whole. If the camera does not answer, the heat is drawn on a plain background (and the page says so); heat recorded at a different camera resolution is not mixed in and is reported.
- **Not verified:** long-running operation (days of continuous events, real database growth, the recorder under sustained load), real cameras and real traffic, and how the charts read over a genuinely busy period. The pages poll every 5-10 seconds; there is no push.

## Next step

Owner verification of Phase 9, then the explicit instruction **"START PHASE 10"**.
