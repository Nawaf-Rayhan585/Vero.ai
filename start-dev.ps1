$root = $PSScriptRoot

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd '$root\backend'; .\venv\Scripts\Activate.ps1; python -m uvicorn main:app --reload --port 8000"
)

Set-Location "$root\desktop"
npm run tauri dev
