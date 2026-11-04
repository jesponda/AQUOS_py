# Arranca AQUOS en modo estable (DEBUG=0, Waitress + WhiteNoise) para la red local.
# Uso:  .\scripts\serve.ps1 [-Port 8000] [-ExtraHosts "aquos.allegion.local"]
param(
    [int]$Port = 8000,
    [string]$ExtraHosts = ""
)
$ErrorActionPreference = "Stop"

$root   = Split-Path -Parent $PSScriptRoot
$data   = Join-Path $env:LOCALAPPDATA "AQUOS"
$python = Join-Path $data "venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $data | Out-Null

# La llave secreta se genera una vez y vive fuera del repositorio.
$keyFile = Join-Path $data "secret_key.txt"
if (-not (Test-Path $keyFile)) {
    & $python -c "from django.core.management.utils import get_random_secret_key as k; print(k(), end='')" |
        Set-Content -NoNewline -Encoding ascii $keyFile
}

# Hosts permitidos: localhost + las IPv4 de este equipo + los extras indicados.
$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    ForEach-Object { $_.IPAddress }
$hosts = @("localhost", "127.0.0.1") + $ips
if ($ExtraHosts) { $hosts += $ExtraHosts.Split(",") }

$env:AQUOS_DEBUG         = "0"
$env:AQUOS_SECRET_KEY    = (Get-Content -Raw $keyFile).Trim()
$env:AQUOS_ALLOWED_HOSTS = ($hosts -join ",")

Set-Location $root
& $python manage.py migrate --noinput
& $python manage.py collectstatic --noinput | Out-Null

Write-Host "AQUOS escuchando en:"
$ips | ForEach-Object { Write-Host "  http://${_}:$Port/" }
& $python -m waitress --listen="0.0.0.0:$Port" --threads=8 config.wsgi:application
