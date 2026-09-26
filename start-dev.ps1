$root = $PSScriptRoot

Set-Location $root
docker compose up -d postgres --wait
if ($LASTEXITCODE -ne 0) {
    Write-Error "PostgreSQL did not start. Is Docker Desktop running, and does .env exist (copy .env.example)?"
    exit 1
}

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    # OPENCV_LOG_LEVEL=SILENT (Phase 17): set before uvicorn starts, not inside Python -
    # confirmed by direct testing that only a process-level env var (not app/camera_
    # testing.py's own runtime cv2.setLogLevel call) suppresses an OpenCV/FFmpeg-internal
    # warning that can otherwise print a camera's stream URL, credentials included.
    "cd '$root\backend'; .\venv\Scripts\Activate.ps1; `$env:OPENCV_LOG_LEVEL = 'SILENT'; alembic upgrade head; python -m uvicorn main:app --reload --port 8000"
)

Set-Location "$root\desktop"
npm run tauri dev
