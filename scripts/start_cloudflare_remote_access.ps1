param(
  [int]$Port = 0,
  [string]$HostName = "127.0.0.1",
  [switch]$Shreya
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo ".jarvis_runtime"
$tokenFile = Join-Path $runtime "web_token.txt"
$mode = if ($Shreya) { "shreya" } else { "jarvis" }
if ($Port -le 0) {
  $Port = if ($Shreya) { 8766 } else { 8765 }
}

$webScript = if ($Shreya) { "run_shreya_jarvis_web.py" } else { "jarvis_web.py" }
$webLog = Join-Path $runtime "jarvis_web_cloudflare_${mode}.log"
$cloudflaredLog = Join-Path $runtime "cloudflared_${mode}.out.log"
$cloudflaredErrLog = Join-Path $runtime "cloudflared_${mode}.err.log"
$webPidFile = Join-Path $runtime "jarvis_web_cloudflare_${mode}.pid"
$cloudflaredPidFile = Join-Path $runtime "cloudflared_${mode}.pid"

New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function New-Token {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Test-Command($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Find-Cloudflared {
  $cmd = Get-Command "cloudflared" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $candidateRoots = @(
    $env:LOCALAPPDATA,
    $env:ProgramFiles,
    ${env:ProgramFiles(x86)},
    $env:ChocolateyInstall
  ) | Where-Object { $_ }
  $candidates = @()
  foreach ($root in $candidateRoots) {
    $candidates += (Join-Path $root "Microsoft\WindowsApps\cloudflared.exe")
    $candidates += (Join-Path $root "cloudflared\cloudflared.exe")
    $candidates += (Join-Path $root "bin\cloudflared.exe")
  }
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate)) {
      return $candidate
    }
  }
  $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path -LiteralPath $wingetRoot) {
    $found = Get-ChildItem -Path $wingetRoot -Recurse -Filter cloudflared.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
      return $found.FullName
    }
  }
  return ""
}

function Stop-PidFile($pidFile) {
  if (Test-Path -LiteralPath $pidFile) {
    $pidValue = (Get-Content -Raw -LiteralPath $pidFile).Trim()
    if ($pidValue) {
      Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  }
}

function Read-TunnelUrl {
  $text = ""
  foreach ($path in @($cloudflaredLog, $cloudflaredErrLog)) {
    if (Test-Path -LiteralPath $path) {
      $text += "`n" + (Get-Content -Raw -LiteralPath $path)
    }
  }
  $match = [regex]::Match($text, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
  if ($match.Success) {
    return $match.Value
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

$cloudflaredExe = Find-Cloudflared
if (-not $cloudflaredExe) {
  throw "cloudflared not found. Install it with: winget install --id Cloudflare.cloudflared -e"
}

$healthUrl = "http://${HostName}:${Port}/api/health"
$webRunning = $false
$webNeedsRestart = $false
try {
  $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
  $webRunning = $true
  if (-not [bool]$health.token_required) {
    $webNeedsRestart = $true
  }
  if ($Shreya -and [string]$health.name -notlike "*Shreya*") {
    $webNeedsRestart = $true
  }
} catch {
  $webRunning = $false
}

if ($webNeedsRestart) {
  Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -match [regex]::Escape($webScript) -and $_.CommandLine -match "--port\s+$Port" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep -Seconds 1
  $webRunning = $false
}

if (-not $webRunning) {
  $webCommand = "`$env:JARVIS_WEB_TOKEN='$token'; cd '$repo'; python $webScript --host $HostName --port $Port *> '$webLog'"
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

Stop-PidFile $cloudflaredPidFile
Remove-Item -LiteralPath $cloudflaredLog, $cloudflaredErrLog -Force -ErrorAction SilentlyContinue

$cloudflaredProcess = Start-Process $cloudflaredExe `
  -ArgumentList @("tunnel", "--url", "http://${HostName}:${Port}", "--no-autoupdate") `
  -RedirectStandardOutput $cloudflaredLog `
  -RedirectStandardError $cloudflaredErrLog `
  -WindowStyle Hidden `
  -PassThru
Set-Content -LiteralPath $cloudflaredPidFile -Value $cloudflaredProcess.Id -Encoding ASCII

$publicUrl = ""
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Milliseconds 750
  $publicUrl = Read-TunnelUrl
  if ($publicUrl) {
    break
  }
  if ($cloudflaredProcess.HasExited) {
    break
  }
}

if (-not $publicUrl) {
  $tail = ""
  foreach ($path in @($cloudflaredErrLog, $cloudflaredLog)) {
    if (Test-Path -LiteralPath $path) {
      $tail += "`n" + ((Get-Content -LiteralPath $path -Tail 30) -join "`n")
    }
  }
  throw "Cloudflare tunnel did not become ready. Check logs: $cloudflaredLog and $cloudflaredErrLog$tail"
}

$remoteHealthOk = $false
try {
  Invoke-RestMethod -Uri "$publicUrl/api/health" -Headers @{ "ngrok-skip-browser-warning" = "1" } -TimeoutSec 10 | Out-Null
  $remoteHealthOk = $true
} catch {}

Write-Host ""
Write-Host "$(if ($Shreya) { 'Shreya JARVIS' } else { 'JARVIS' }) Cloudflare remote access is ready." -ForegroundColor Green
Write-Host ""
Write-Host "Enter this in the Android app:"
Write-Host "Server URL: $publicUrl" -ForegroundColor Cyan
Write-Host "API token : $token" -ForegroundColor Cyan
Write-Host ""
if (-not $remoteHealthOk) {
  Write-Host "Tunnel URL was created, but /api/health did not respond yet. Wait a few seconds and tap Test HTTPS." -ForegroundColor Yellow
}
Write-Host "Quick Tunnel URLs can change after restart."
Write-Host "Laptop must stay ON, online, and not asleep."
Write-Host "To stop remote access: .\scripts\stop_remote_access.ps1"
