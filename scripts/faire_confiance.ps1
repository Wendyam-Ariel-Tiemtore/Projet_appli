# Fait confiance à l'autorité locale du proxy HTTPS (Windows), pour supprimer l'avertissement du navigateur.
# À lancer depuis le dossier du projet, une fois les conteneurs démarrés :
#   powershell -ExecutionPolicy Bypass -File scripts\faire_confiance.ps1
# Le certificat racine est ajouté au magasin de l'utilisateur courant (aucun droit administrateur requis) ;
# Windows demande une confirmation. Pour le retirer : certmgr.msc, Autorités de certification racines de confiance.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$fichier = Join-Path (Get-Location) "autorite-locale.crt"
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt $fichier
if (-not (Test-Path $fichier)) {
    Write-Error "Certificat introuvable : vérifiez que les conteneurs tournent (docker compose ps)."
}
certutil -user -addstore Root $fichier | Out-Null
Write-Host ""
Write-Host "Autorité locale ajoutée. Fermez toutes les fenêtres du navigateur, puis ouvrez https://localhost"
