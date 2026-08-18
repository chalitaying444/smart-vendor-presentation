<#
  เปิดระบบให้เข้าจากภายนอกผ่าน ngrok

  ngrok รุ่นฟรีสุ่ม URL ใหม่ทุกครั้งที่เปิด และมีสี่ที่ที่ต้องใส่ URL นั้นให้ตรงกัน
  (FRONTEND_URL, CORS_ORIGINS, MS_REDIRECT_URI, DEV_ORIGINS) พลาดที่เดียวก็ล็อกอินไม่ได้
  สคริปต์นี้อ่าน URL จาก ngrok ที่เปิดอยู่แล้วเติมให้ครบทุกที่

  วิธีใช้
      1) เปิด backend และ frontend ตามปกติ
      2) เปิดอีกหน้าต่าง:  ngrok http 3000
      3) .\run-ngrok.ps1
      4) รีสตาร์ท backend และ next dev ตามที่สคริปต์บอก

  เลิกใช้ ngrok กลับมาเป็น localhost:   .\run-ngrok.ps1 -Revert
#>
[CmdletBinding()]
param(
    [switch]$Revert,
    [int]$Port = 0          # เว้นไว้ = อ่านพอร์ตจาก tunnel ที่เปิดอยู่จริง
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$envFile = Join-Path $root ".env"
$feEnvFile = Join-Path $root "frontend\.env.local"

function Set-EnvValue([string]$file, [string]$key, [string]$value) {
    if (-not (Test-Path $file)) { New-Item -ItemType File -Path $file -Force | Out-Null }
    $pattern = "^$([regex]::Escape($key))="
    $found = $false
    $out = @()
    foreach ($line in @(Get-Content -Path $file -Encoding UTF8)) {
        if ($line -match $pattern) { $out += "$key=$value"; $found = $true }
        else { $out += $line }
    }
    if (-not $found) { $out += "$key=$value" }
    # เขียนแบบ UTF-8 ที่ไม่มี BOM — Set-Content ของ PowerShell 5.1 ใส่ BOM ให้เสมอ
    # แล้วตัวอ่าน .env ฝั่ง Python จะได้ชื่อคีย์แรกเพี้ยนเป็น "\ufeffMONGODB_URI"
    # ผลคือต่อฐานข้อมูลไม่ได้ โดยที่ไฟล์ยังดูปกติทุกอย่างเวลาเปิดดู
    [System.IO.File]::WriteAllLines($file, $out, (New-Object System.Text.UTF8Encoding($false)))
}

function Get-BackendPort {
    $m = Select-String -Path $envFile -Pattern "^BACKEND_PORT=(\d+)" | Select-Object -First 1
    if ($m) { return [int]$m.Matches[0].Groups[1].Value }
    return 8000
}

function Get-DevPort {
    # อ่านจาก package.json (เช่น "next dev -p 5000") ไม่ใช่เดาเอาเอง
    $pkg = Join-Path $root "frontend\package.json"
    if (Test-Path $pkg) {
        $dev = (Get-Content $pkg -Raw | ConvertFrom-Json).scripts.dev
        if ($dev -match "-p\s+(\d+)") { return [int]$Matches[1] }
    }
    return 3000
}

# ---------------------------------------------------------------- เลิกใช้ ngrok
if ($Revert) {
    if ($Port -eq 0) { $Port = Get-DevPort }
    Set-EnvValue $envFile "FRONTEND_URL"    "http://localhost:$Port"
    Set-EnvValue $envFile "CORS_ORIGINS"    "http://localhost:$Port"
    Set-EnvValue $envFile "MS_REDIRECT_URI" "http://localhost:$Port/api/auth/ms/callback"
    Set-EnvValue $envFile "COOKIE_SECURE"   "false"
    Set-EnvValue $feEnvFile "DEV_ORIGINS"   ""
    Write-Host "`nกลับมาใช้ localhost:$Port แล้ว" -ForegroundColor Green
    Write-Host "อย่าลืมรีสตาร์ท backend และ next dev · และใน Azure ต้องมี" -ForegroundColor Yellow
    Write-Host "    http://localhost:$Port/api/auth/ms/callback" -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------- หา URL ของ ngrok
Write-Host "`nกำลังอ่าน URL จาก ngrok ที่เปิดอยู่..." -ForegroundColor Cyan
try {
    $api = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 5
} catch {
    Write-Host "ต่อ ngrok ไม่ได้ (http://127.0.0.1:4040)" -ForegroundColor Red
    Write-Host "เปิด ngrok ก่อนในอีกหน้าต่างหนึ่ง:  ngrok http $Port" -ForegroundColor Yellow
    exit 1
}

$tunnel = $api.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
if (-not $tunnel) { $tunnel = $api.tunnels | Select-Object -First 1 }
if (-not $tunnel) {
    Write-Host "ngrok เปิดอยู่แต่ยังไม่มี tunnel — สั่ง  ngrok http $Port  ก่อน" -ForegroundColor Red
    exit 1
}

$public = $tunnel.public_url.TrimEnd('/')
$target = $tunnel.config.addr
Write-Host "    เจอ tunnel: $public  ->  $target"

# พอร์ตปลายทางเอาจาก tunnel จริง ไม่ใช่ให้คนมาจำเองว่าโปรเจกต์นี้ dev ที่พอร์ตอะไร
if ($target -match ":(\d+)$") { $tunnelPort = [int]$Matches[1] } else { $tunnelPort = 0 }
if ($Port -eq 0) { $Port = if ($tunnelPort -gt 0) { $tunnelPort } else { Get-DevPort } }

$backendPort = Get-BackendPort
if ($tunnelPort -eq $backendPort) {
    Write-Host "`nคำเตือน: tunnel ชี้ไปที่ backend ($target) ไม่ใช่ frontend" -ForegroundColor Yellow
    Write-Host "ควรเปิดทะลุที่ frontend เพราะ Next ส่งต่อ /api ไปหลังบ้านให้อยู่แล้ว" -ForegroundColor Yellow
    Write-Host "เปิดแบบนี้จะได้แต่ API ไม่มีหน้าเว็บ · frontend ของโปรเจกต์นี้อยู่พอร์ต $(Get-DevPort)" -ForegroundColor Yellow
    $ans = Read-Host "จะใช้ URL นี้ต่อไหม (y/N)"
    if ($ans -ne "y") { exit 1 }
}

$ngrokHost = ([Uri]$public).Host
$redirect = "$public/api/auth/ms/callback"
$localOrigin = "http://localhost:$Port"

# ---------------------------------------------------------------- เขียนค่าลงไฟล์
Set-EnvValue $envFile "FRONTEND_URL"    $public
Set-EnvValue $envFile "CORS_ORIGINS"    "$localOrigin,$public"
Set-EnvValue $envFile "MS_REDIRECT_URI" $redirect
Set-EnvValue $envFile "COOKIE_SECURE"   "true"
Set-EnvValue $feEnvFile "DEV_ORIGINS"   $ngrokHost

Write-Host "`nตั้งค่าให้แล้ว:" -ForegroundColor Green
Write-Host "    .env  FRONTEND_URL    = $public        (ลิงก์ที่ส่งให้ผู้ขายจะใช้ URL นี้)"
Write-Host "    .env  CORS_ORIGINS    = $localOrigin,$public"
Write-Host "    .env  MS_REDIRECT_URI = $redirect"
Write-Host "    .env  COOKIE_SECURE   = true            (ngrok เป็น https)"
Write-Host "    frontend\.env.local  DEV_ORIGINS = $ngrokHost"

Write-Host "`nอีกสองอย่างที่ต้องทำเอง" -ForegroundColor Cyan
Write-Host "  1) Azure Portal > App registrations > แอปของเรา > Authentication > Web > Redirect URIs"
Write-Host "     เพิ่ม (ต้องตรงเป๊ะ ห้ามมี / ปิดท้าย):" -ForegroundColor Yellow
Write-Host "     $redirect" -ForegroundColor Yellow
Write-Host "  2) รีสตาร์ท backend และ next dev — ทั้งคู่อ่านค่าพวกนี้ตอนสตาร์ทครั้งเดียว"

Write-Host "`nข้อควรรู้" -ForegroundColor Cyan
@"
  - COOKIE_SECURE=true แล้ว จะเข้าผ่าน http://localhost:$Port ไม่ได้ (คุกกี้จะไม่ถูกส่ง)
    ระหว่างนี้ให้ใช้ $public · เลิกใช้แล้วสั่ง  .\run-ngrok.ps1 -Revert
  - ngrok รุ่นฟรีสุ่ม URL ใหม่ทุกครั้งที่เปิด ต้องรันสคริปต์นี้ใหม่และไปเพิ่ม URI ใน Azure ทุกครั้ง
    ถ้าสมัคร static domain ของ ngrok ไว้ (ฟรี 1 โดเมน) แล้วสั่ง
        ngrok http $Port --domain=ชื่อโดเมนของคุณ.ngrok-free.app
    จะตั้งค่าครั้งเดียวจบ ไม่ต้องแก้ Azure อีก
  - หน้าเตือนของ ngrok ("You are about to visit...") ฝั่งเรียก API ข้ามให้แล้วในโค้ด
    แต่ตอนผู้ขายเปิดลิงก์ครั้งแรกจะเจอหน้านี้หนึ่งครั้ง ให้กด Visit Site ได้เลย
"@
