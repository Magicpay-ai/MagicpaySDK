# Demo mağazayı başlatır. Anahtarlar gizli girişle okunur, dosyaya ya da komut geçmişine yazılmaz.
#   .\start.ps1               canlı ortam (https://tr.magicpay.ai), canlı API anahtarı
#   .\start.ps1 -Ortam test   test ortamı (https://trdev.magicpay.ai), test API anahtarı
param(
    [ValidateSet("canli", "test")] [string]$Ortam = "canli",
    [int]$Port = 8010
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Kurulum yapılıyor (.venv)..."
    python -m venv .venv
    & $python -m pip install -q -r requirements.txt
}

if ($Ortam -eq "canli") {
    $env:MAGICPAY_BASE_URL = "https://tr.magicpay.ai"
    Write-Host ""
    Write-Host "CANLI ORTAM: gerçek kartlardan gerçek tutar çekilir. Küçük tutarla deneyin, aynı gün iade edin." -ForegroundColor Yellow
} else {
    $env:MAGICPAY_BASE_URL = "https://trdev.magicpay.ai"
}

$k = Read-Host "MAGICPAY_API_KEY ($Ortam)" -AsSecureString
$s = Read-Host "MAGICPAY_SECRET_KEY ($Ortam)" -AsSecureString
$env:MAGICPAY_API_KEY = [Net.NetworkCredential]::new("", $k).Password
$env:MAGICPAY_SECRET_KEY = [Net.NetworkCredential]::new("", $s).Password
Remove-Variable k, s
$env:DEMO_PUBLIC_URL = "http://127.0.0.1:$Port"

$url = "http://127.0.0.1:$Port"
Write-Host "Demo açılıyor: $url  (kapatmak için Ctrl+C)"
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 3; Start-Process $u } -ArgumentList $url | Out-Null
try {
    & $python -m uvicorn app:app --host 127.0.0.1 --port $Port --no-access-log
} finally {
    Remove-Item Env:MAGICPAY_API_KEY, Env:MAGICPAY_SECRET_KEY -ErrorAction SilentlyContinue
}
