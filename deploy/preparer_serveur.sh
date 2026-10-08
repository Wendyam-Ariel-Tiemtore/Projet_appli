#!/usr/bin/env bash
# Préparation et durcissement d'un serveur Ubuntu 24.04 LTS neuf pour Analyste académique.
# Usage (connecté en root sur le serveur) :  bash preparer_serveur.sh [nom_utilisateur]
# Prérequis : votre clé SSH publique a été ajoutée au serveur lors de sa création (fichier
# /root/.ssh/authorized_keys). Sans elle, le script s'arrête avant de couper l'accès par mot de passe.
set -euo pipefail

UTILISATEUR="${1:-analyste}"
[ "$(id -u)" -eq 0 ] || { echo "Lancez ce script en root (ou avec sudo)."; exit 1; }
[ -s /root/.ssh/authorized_keys ] || {
  echo "Aucune clé SSH trouvée dans /root/.ssh/authorized_keys : ajoutez votre clé publique avant de continuer."
  exit 1
}
export DEBIAN_FRONTEND=noninteractive

echo "==> 1/7 Mise à jour du système"
apt-get update -q
apt-get -y -q upgrade
apt-get install -y -q ufw fail2ban unattended-upgrades git curl ca-certificates gnupg

echo "==> 2/7 Utilisateur d'administration « $UTILISATEUR » (connexion par clé uniquement)"
if ! id "$UTILISATEUR" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$UTILISATEUR"
  usermod -aG sudo "$UTILISATEUR"
  echo "Choisissez le mot de passe de « $UTILISATEUR » (il servira uniquement pour la commande sudo) :"
  passwd "$UTILISATEUR"
fi
install -d -m 700 -o "$UTILISATEUR" -g "$UTILISATEUR" "/home/$UTILISATEUR/.ssh"
install -m 600 -o "$UTILISATEUR" -g "$UTILISATEUR" /root/.ssh/authorized_keys "/home/$UTILISATEUR/.ssh/authorized_keys"

echo "==> 3/7 Durcissement de SSH (pas de root, pas de mot de passe)"
cat > /etc/ssh/sshd_config.d/99-durcissement.conf <<CONF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowUsers $UTILISATEUR
CONF
sshd -t
systemctl reload ssh

echo "==> 4/7 Pare-feu : seuls SSH, HTTP et HTTPS sont ouverts"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> 5/7 Protection contre les attaques par force brute (fail2ban)"
cat > /etc/fail2ban/jail.d/sshd.local <<CONF
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
CONF
systemctl enable --now fail2ban
systemctl restart fail2ban

echo "==> 6/7 Mises à jour de sécurité automatiques"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<CONF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
CONF
systemctl enable --now unattended-upgrades

echo "==> 7/7 Docker (dépôt officiel), journaux bornés"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com -o /tmp/installer-docker.sh
  sh /tmp/installer-docker.sh
  rm -f /tmp/installer-docker.sh
fi
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<CONF
{
  "log-driver": "local",
  "log-opts": {"max-size": "20m", "max-file": "5"},
  "live-restore": true,
  "no-new-privileges": true
}
CONF
systemctl restart docker
usermod -aG docker "$UTILISATEUR"

cat <<FIN

Serveur prêt.
IMPORTANT : avant de fermer cette fenêtre, ouvrez une NOUVELLE fenêtre PowerShell sur votre ordinateur et
vérifiez que cette commande fonctionne :   ssh $UTILISATEUR@$(curl -fsS -4 https://ifconfig.me 2>/dev/null || echo ADRESSE_IP)
La connexion directe en root est désormais refusée.
FIN
