$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment missing. Run .\scripts\setup.ps1 first."
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; ..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "API:  http://localhost:8000/docs"
Write-Host "UI:   http://localhost:5173"
