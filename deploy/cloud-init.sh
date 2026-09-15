#!/bin/bash
# Oracle Cloud "Initialization script" (cloud-init user-data) for the PikaRAG
# instance. Paste this into Compute -> Create Instance -> Show advanced
# options -> Initialization script, or pass it via --user-data-file to the
# OCI CLI. Runs once, as root, on first boot of the Ubuntu 22.04 ARM image.
#
# What this does NOT do: write .env, or enable/start the bot. Those need a
# real Discord token + LLM_HOST value, which don't belong in instance
# metadata (readable via the OCI console by anyone with access to the
# instance). SSH in afterward to finish those two steps -- see
# docs/DEPLOYMENT.md sections 2 and 4.

set -euo pipefail

REPO_URL="https://github.com/knguyen0923/PikaRAG.git"
APP_DIR="/opt/pikarag"

apt-get update
apt-get install -y software-properties-common
add-apt-repository -y universe
apt-get update
apt-get install -y python3.11 python3.11-venv git

if ! id -u pikarag &>/dev/null; then
  # -M (not -m): skip populating $APP_DIR from /etc/skel. With -m, useradd
  # writes .bashrc/.profile/.bash_logout into $APP_DIR, so the directory is
  # never empty by the time git clone runs into it below, and clone fails
  # with "destination path already exists and is not an empty directory."
  useradd -r -M -d "$APP_DIR" -s /usr/sbin/nologin pikarag
fi

mkdir -p "$APP_DIR"
chown pikarag:pikarag "$APP_DIR"

if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u pikarag git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
sudo -u pikarag python3.11 -m venv .venv
sudo -u pikarag .venv/bin/pip install -r requirements.txt

if [ ! -f "$APP_DIR/.env" ]; then
  sudo -u pikarag cp .env.example .env
  chmod 600 "$APP_DIR/.env"
fi

# Install the systemd units now so they're in place, but leave them
# disabled -- enabling before .env is filled in would crash-loop.
cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
install -m 0440 deploy/sudoers-pikarag /etc/sudoers.d/pikarag
systemctl daemon-reload

echo "PikaRAG bootstrap complete. SSH in, edit $APP_DIR/.env, then run:" \
     "sudo systemctl enable --now pikarag-bot.service" \
     "sudo systemctl enable --now pikarag-refresh-pokeapi.timer" \
     "sudo systemctl enable --now pikarag-refresh-pikalytics.timer" \
     > /var/log/pikarag-bootstrap-done.log
