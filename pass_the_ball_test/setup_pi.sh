#!/usr/bin/env bash
# setup_pi.sh — One-shot setup for any micro:bit game on Raspberry Pi (B+ or Pi 5)
#
# Run from the repo root:
#   bash setup_pi.sh
#
# What it does:
#   1. Installs Python deps from computer_app/requirements.txt
#   2. Adds the current user to the 'dialout' group (serial port access)
#   3. Installs and enables a systemd service (auto-start on boot)
#      — service name is derived from the repo folder name

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/computer_app"
CURRENT_USER="$(whoami)"

# Derive a clean service name from the repo folder name
#   e.g. "pass_the_ball_test" → "pass-the-ball-test"
REPO_NAME="$(basename "$SCRIPT_DIR")"
SERVICE_NAME="${REPO_NAME//_/-}"   # replace underscores with dashes

echo "=== Micro:bit Game — Pi setup ==="
echo "Project       : $REPO_NAME"
echo "Service name  : $SERVICE_NAME"
echo "App directory : $APP_DIR"
echo "Running as    : $CURRENT_USER"
echo ""

# ── 1. Python dependencies ────────────────────────────────────────────────────
echo "[1/3] Installing Python dependencies..."
pip3 install --break-system-packages -r "$APP_DIR/requirements.txt" 2>/dev/null \
  || pip3 install -r "$APP_DIR/requirements.txt"
echo "      Done."

# ── 2. Serial port permission ─────────────────────────────────────────────────
echo "[2/3] Adding '$CURRENT_USER' to the 'dialout' group (serial access)..."
sudo usermod -aG dialout "$CURRENT_USER"
echo "      Done. (Takes effect on next login — or run: newgrp dialout)"

# ── 3. systemd service ────────────────────────────────────────────────────────
echo "[3/3] Installing systemd service '$SERVICE_NAME'..."

cat > "/tmp/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Micro:bit Game — $REPO_NAME dashboard
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 app.py
Restart=on-failure
RestartSec=5
TimeoutStartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo cp "/tmp/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
echo "      Done."

echo ""
echo "=== Setup complete ==="
echo ""
echo "Dashboard URL : http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME    — check if running"
echo "  journalctl -u $SERVICE_NAME -f         — live log"
echo "  sudo systemctl stop $SERVICE_NAME      — stop the server"
echo "  sudo systemctl disable $SERVICE_NAME   — disable auto-start"
