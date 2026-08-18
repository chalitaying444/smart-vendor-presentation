# Run Next.js dev server (http://localhost:3000)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Next.js 16 requires Node.js 20.9 or newer
$nodeVer = (node --version) -replace '^v', ''
$major = [int]($nodeVer.Split('.')[0])
$minor = [int]($nodeVer.Split('.')[1])
if ($major -lt 20 -or ($major -eq 20 -and $minor -lt 9)) {
    Write-Host "ERROR: Node.js $nodeVer is too old. Next.js needs 20.9 or newer." -ForegroundColor Red
    Write-Host "Download the LTS installer from https://nodejs.org/ then run this script again." -ForegroundColor Yellow
    exit 1
}

Push-Location (Join-Path $root "frontend")
if (-not (Test-Path "node_modules")) {
    Write-Host "node_modules not found - running npm install..." -ForegroundColor Yellow
    npm install
}
npm run dev
Pop-Location
