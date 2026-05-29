param(
  [int]$Port = 8765,
  [string]$HostName = "127.0.0.1",
  [string]$NgrokAuthtoken = ""
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo ".jarvis_runtime"
$tokenFile = Join-Path $runtime "web_token.txt"
$webLog = Join-Path $runtime "jarvis_web_remote.log"
$ngrokLog = Join-Path $runtime "ngrok_remote.out.log"
$ngrokErrLog = Join-Path $runtime "ngrok_remote.err.log"
$webPidFile = Join-Path $runtime "jarvis_web_remote.pid"
$ngrokPidFile = Join-Path $runtime "ngrok_remote.pid"

New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function New-Token {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Test-Command($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Find-Ngrok {
  $cmd = Get-Command "ngrok" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\ngrok.exe")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }
  $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path -LiteralPath $wingetRoot) {
    $found = Get-ChildItem -Path $wingetRoot -Recurse -Filter ngrok.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
      return $found.FullName
    }
  }
  return ""
}

if ($env:JARVIS_WEB_TOKEN -and $env:JARVIS_WEB_TOKEN.Trim().Length -ge 24) {
  $token = $env:JARVIS_WEB_TOKEN.Trim()
} elseif (Test-Path -LiteralPath $tokenFile) {
  $token = (Get-Content -Raw -LiteralPath $tokenFile).Trim()
} else {
  $token = New-Token
  Set-Content -LiteralPath $tokenFile -Value $token -Encoding ASCII
}

if ($token.Length -lt 24) {
  throw "JARVIS_WEB_TOKEN must be at least 24 characters."
}

if (-not (Test-Command "python")) {
  throw "python not found in PATH. Install Python 3.10 and try again."
}

$ngrokExe = Find-Ngrok
if (-not $ngrokExe) {
  throw "ngrok not found in PATH. Install it with: winget install --id Ngrok.Ngrok -e"
}

if ($NgrokAuthtoken.Trim()) {
  & $ngrokExe config add-authtoken $NgrokAuthtoken.Trim() | Out-Null
}

$healthUrl = "http://${HostName}:${Port}/api/health"
$webRunning = $false
try {
  Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 | Out-Null
  $webRunning = $true
} catch {
  $webRunning = $false
}

if (-not $webRunning) {
  $webCommand = "`$env:JARVIS_WEB_TOKEN='$token'; cd '$repo'; python jarvis_web.py --host $HostName --port $Port *> '$webLog'"
  $webProcess = Start-Process powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $webCommand) -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $webPidFile -Value $webProcess.Id -Encoding ASCII

  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
      Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2 | Out-Null
      $ready = $true
      break
    } catch {}
  }
  if (-not $ready) {
    throw "JARVIS web did not start. Check log: $webLog"
  }
}

$existingTunnel = $null
try {
  $existing = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
  $existingTunnel = $existing.tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
} catch {}

if (-not $existingTunnel) {
  $ngrokProcess = Start-Process $ngrokExe -ArgumentList @("http", "http://${HostName}:${Port}", "--log=stdout") -RedirectStandardOutput $ngrokLog -RedirectStandardError $ngrokErrLog -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $ngrokPidFile -Value $ngrokProcess.Id -Encoding ASCII
}

$publicUrl = ""
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 750
  try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
    $tunnel = $tunnels.tunnels | Where-Object { $_.public_url -like "https://*" } | Select-Object -First 1
    if ($tunnel) {
      $publicUrl = [string]$tunnel.public_url
      break
    }
  } catch {}
}

if (-not $publicUrl) {
  throw "Ngrok tunnel did not become ready. If this is first use, run: ngrok config add-authtoken YOUR_NGROK_TOKEN. Check logs: $ngrokLog and $ngrokErrLog"
}

Write-Host ""
Write-Host "JARVIS remote access is ready." -ForegroundColor Green
Write-Host ""
Write-Host "Enter this in the Android app:"
Write-Host "Server URL: $publicUrl" -ForegroundColor Cyan
Write-Host "API token : $token" -ForegroundColor Cyan
Write-Host ""
Write-Host "Laptop must stay ON, online, and not asleep."
Write-Host "To stop remote access: .\scripts\stop_remote_access.ps1"
