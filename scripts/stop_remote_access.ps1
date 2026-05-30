$ErrorActionPreference = "SilentlyContinue"

$repo = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $repo ".jarvis_runtime"
$pidFiles = @(
  (Join-Path $runtime "ngrok_remote.pid"),
  (Join-Path $runtime "jarvis_web_remote.pid"),
  (Join-Path $runtime "cloudflared_jarvis.pid"),
  (Join-Path $runtime "cloudflared_shreya.pid"),
  (Join-Path $runtime "jarvis_web_cloudflare_jarvis.pid"),
  (Join-Path $runtime "jarvis_web_cloudflare_shreya.pid")
)

foreach ($pidFile in $pidFiles) {
  if (Test-Path -LiteralPath $pidFile) {
    $pidValue = (Get-Content -Raw -LiteralPath $pidFile).Trim()
    if ($pidValue) {
      Stop-Process -Id ([int]$pidValue) -Force
    }
    Remove-Item -LiteralPath $pidFile -Force
  }
}

Write-Host "JARVIS remote access stop requested."
