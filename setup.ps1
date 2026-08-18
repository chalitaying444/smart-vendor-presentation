# ============================================================
#  Vendor App - first-time setup
#  Run from E:\vendor_app :
#    powershell -ExecutionPolicy Bypass -File .\setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "==> Checking Python" -ForegroundColor Cyan
python --version

# ---------- 1) create virtual environment ----------
$venv = Join-Path $root ".venv"
if (Test-Path $venv) {
    Write-Host "==> .venv already exists, skipping creation" -ForegroundColor Yellow
} else {
    Write-Host "==> Creating virtual environment at .venv" -ForegroundColor Cyan
    python -m venv $venv
}

$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "ERROR: .venv\Scripts\python.exe not found." -ForegroundColor Red
    exit 1
}

# ---------- 2) backend dependencies ----------
Write-Host "==> Upgrading pip" -ForegroundColor Cyan
& $py -m pip install --upgrade pip

Write-Host "==> Installing packages from backend\requirements.txt" -ForegroundColor Cyan
& $py -m pip install -r (Join-Path $root "backend\requirements.txt")

# ---------- 3) frontend dependencies ----------
$nodeVer = (node --version) -replace '^v', ''
Write-Host "==> Node.js version: $nodeVer" -ForegroundColor Cyan
$major = [int]($nodeVer.Split('.')[0])
$minor = [int]($nodeVer.Split('.')[1])
if ($major -lt 20 -or ($major -eq 20 -and $minor -lt 9)) {
    Write-Host "ERROR: Node.js $nodeVer is too old. Next.js needs 20.9 or newer." -ForegroundColor Red
    Write-Host "Install the LTS build from https://nodejs.org/ then run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "==> Installing npm packages for frontend" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
npm install
Pop-Location

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "  1. Edit .env  -> MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET / MONGODB_URI"
Write-Host "  2. Terminal 1 -> .\run-backend.ps1    http://localhost:8000/docs"
Write-Host "  3. Terminal 2 -> .\run-frontend.ps1   http://localhost:3000"
