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
    "cd '$root\backend'; .\venv\Scripts\Activate.ps1; alembic upgrade head; python -m uvicorn main:app --reload --port 8000"
)

Set-Location "$root\desktop"
npm run tauri dev
