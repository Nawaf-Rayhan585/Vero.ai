# AI Vision

Desktop app for running YOLO-based object detection/segmentation/pose estimation on images and videos.

## Architecture

- **backend/** — FastAPI server. In-memory job store, exposes `/jobs` endpoints, runs detection in a background task.
- **ai-engine/** — YOLO detection pipeline (`Detector` class). Imported directly by `backend/` (not a separate service).
- **desktop/** — Tauri + React UI. Talks to the backend over HTTP at `http://127.0.0.1:8000`.

## Prerequisites

- Python 3.10+
- Node.js 18+
- Rust toolchain (for Tauri) — see https://tauri.app/start/prerequisites/

## First-time setup

```powershell
# Backend (also covers ai-engine's dependencies, since backend imports it directly)
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision\backend"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
deactivate

# Desktop
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision\desktop"
npm install
```

## Running the app (development)

Run these in two separate PowerShell terminals.

```powershell
# Terminal 1 — backend API
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision\backend"
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000
```

```powershell
# Terminal 2 — desktop app
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision\desktop"
npm run tauri dev
```

Or use the bundled start script, which launches the backend in a new window and then starts the desktop dev app:

```powershell
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision"
.\start-dev.ps1
```

Once both are running: click **Select Video/Image** in the app, choose a model and confidence threshold under **Settings**, then click **Run Detection**.

The first detection run for a given model downloads its YOLO weights (e.g. `yolov8n.pt`) into `backend/` and caches them there for subsequent runs.

## Building a Windows installer

```powershell
cd "F:\AI Dev\AI Vision SaaS Platform\ai-vision\desktop"
npm run tauri build
```

This produces an MSI and an NSIS installer under `desktop/src-tauri/target/release/bundle/`. The bundled app expects the backend to be running separately at `http://127.0.0.1:8000` — it does not launch or embed the Python backend.

## Notes / current limitations (V1)

- Job store is in-memory only; restarting the backend clears all job history.
- No auth.
- The desktop build does not package or auto-start the backend/ai-engine — those must be running (or installed) alongside the app.
