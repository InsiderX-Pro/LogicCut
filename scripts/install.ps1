param(
  [ValidateSet("lite", "creator", "full")]
  [string]$Profile = "lite"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

python scripts/bootstrap.py --profile $Profile

if ($Profile -eq "full") {
  Write-Host "Full profile on Windows is experimental. For GPU video translation, use WSL2 and scripts/install.sh --profile full."
}
