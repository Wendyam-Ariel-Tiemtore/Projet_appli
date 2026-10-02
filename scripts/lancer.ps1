# Lancement sans Docker (Windows PowerShell) : https://localhost:8443
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\pip.exe install -r requirements.txt
}
if (-not (Test-Path "donnees\certificats\certificat.pem")) { .\.venv\Scripts\python.exe scripts\certificat_local.py }
Write-Host "Application disponible sur https://localhost:8443 (arret : Ctrl+C)"
.\.venv\Scripts\uvicorn.exe --factory analyste.web.app:create_app --host 127.0.0.1 --port 8443 `
  --ssl-keyfile donnees\certificats\cle.pem --ssl-certfile donnees\certificats\certificat.pem `
  --no-server-header --workers 1
