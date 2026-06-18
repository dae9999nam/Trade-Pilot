param(
    [string]$GatewayToken,
    [string]$CreonAccountNo,
    [string]$CreonGoodsCode = "01",
    [int]$Port = 8765,
    [string]$CreonInstallerPath,
    [switch]$AllowLiveTrading,
    [switch]$UnderstandLossRisk,
    [switch]$OpenFirewall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Value {
    param(
        [string]$Name,
        [string]$Value
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required."
    }
}

$isWindowsOs = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
if (-not $isWindowsOs) {
    throw "CREON gateway setup must run on Windows."
}

Require-Value -Name "GatewayToken" -Value $GatewayToken
Require-Value -Name "CreonAccountNo" -Value $CreonAccountNo

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$gatewayDir = Join-Path $repoRoot "gateway"
$venvDir = Join-Path $gatewayDir ".venv"
$envFile = Join-Path $gatewayDir ".env"
$runScript = Join-Path $gatewayDir "run-creon-gateway.ps1"

if ($CreonInstallerPath) {
    if (-not (Test-Path $CreonInstallerPath)) {
        throw "CREON installer was not found: $CreonInstallerPath"
    }
    Write-Host "Launching CREON Plus installer interactively. Complete installation and security-module setup in the Windows UI."
    Start-Process -FilePath $CreonInstallerPath -Wait
}

Write-Host "Checking for 32-bit Python 3.11 launcher..."
& py -3.11-32 -c "import struct; assert struct.calcsize('P') * 8 == 32"

if (-not (Test-Path $venvDir)) {
    Write-Host "Creating 32-bit Python virtual environment..."
    & py -3.11-32 -m venv $venvDir
}

$python = Join-Path $venvDir "Scripts\python.exe"
Write-Host "Installing gateway dependencies..."
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $gatewayDir "requirements.txt")

$allowLive = if ($AllowLiveTrading) { "true" } else { "false" }
$understandRisk = if ($UnderstandLossRisk) { "true" } else { "false" }

@"
GATEWAY_TOKEN=$GatewayToken
CREON_ACCOUNT_NO=$CreonAccountNo
CREON_GOODS_CODE=$CreonGoodsCode
ALLOW_LIVE_TRADING=$allowLive
I_UNDERSTAND_LOSS_RISK=$understandRisk
"@ | Set-Content -Path $envFile -Encoding UTF8

@"
Set-StrictMode -Version Latest
`$ErrorActionPreference = "Stop"
Set-Location "`$PSScriptRoot"
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port $Port
"@ | Set-Content -Path $runScript -Encoding UTF8

if ($OpenFirewall) {
    Write-Host "Opening Windows Firewall inbound TCP port $Port for the CREON gateway..."
    New-NetFirewallRule `
        -DisplayName "Trade-pilot CREON Gateway $Port" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $Port `
        -Action Allow | Out-Null
}

Write-Host "Gateway setup complete."
Write-Host "Next: log in to CREON Plus in this Windows desktop session, then run:"
Write-Host "  $runScript"
