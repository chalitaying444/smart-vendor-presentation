# Run FastAPI (Swagger UI: http://localhost:8000/docs)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "ERROR: .venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Push-Location (Join-Path $root "backend")
& $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
Pop-Location
