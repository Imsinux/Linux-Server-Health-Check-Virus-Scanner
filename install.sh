#!/bin/bash
# install.sh — Setup script for the Linux Health Check & Virus Scanner
# Run with: sudo bash install.sh

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTHCHECK_DIR="/healthcheck"
SERVICE_FILE="/etc/systemd/system/healthcheck.service"
TIMER_FILE="/etc/systemd/system/healthcheck.timer"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║     🔧  Health Check & Virus Scanner Installer       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Check root ─────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run as root: sudo bash install.sh"
  exit 1
fi

# ── Detect package manager ─────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
  PKG="apt-get"
elif command -v yum &>/dev/null; then
  PKG="yum"
elif command -v dnf &>/dev/null; then
  PKG="dnf"
else
  echo "⚠️  Cannot detect package manager. Install ClamAV manually."
  PKG=""
fi

# ── Install ClamAV ─────────────────────────────────────────────────────────
echo "[1/5] Installing ClamAV..."
if [ -n "$PKG" ]; then
  if command -v apt-get &>/dev/null; then
    apt-get update -qq
    apt-get install -y clamav clamav-daemon clamav-freshclam
  else
    $PKG install -y clamav clamav-update
  fi
  echo "✅ ClamAV installed."
else
  echo "⚠️  Skipping ClamAV install (no package manager detected)."
fi

# ── Update ClamAV database ─────────────────────────────────────────────────
echo "[2/5] Updating ClamAV virus database..."
# Stop clamav-freshclam service if running to avoid lock conflict
systemctl stop clamav-freshclam 2>/dev/null || true
freshclam || echo "⚠️  freshclam update failed (may need manual run: sudo freshclam)"
systemctl start clamav-freshclam 2>/dev/null || true
echo "✅ Virus database updated."

# ── Install Python dependencies ────────────────────────────────────────────
echo "[3/5] Checking Python dependencies..."
python3 --version || { echo "❌ Python 3 not found."; exit 1; }
echo "✅ Python 3 is available. No extra pip packages required."

# ── Create /healthcheck output directory ───────────────────────────────────
echo "[4/5] Creating output directory $HEALTHCHECK_DIR..."
mkdir -p "$HEALTHCHECK_DIR"
chmod 755 "$HEALTHCHECK_DIR"
echo "✅ Directory $HEALTHCHECK_DIR ready."

# ── Install systemd service & timer ────────────────────────────────────────
echo "[5/5] Installing systemd service and timer..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Server Health Check & Virus Scanner
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ${APP_DIR}/healthcheck.py --output-dir ${HEALTHCHECK_DIR}
StandardOutput=journal
StandardError=journal
User=root

[Install]
WantedBy=multi-user.target
EOF

cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run Health Check every 6 hours
Requires=healthcheck.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Unit=healthcheck.service
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable healthcheck.timer
systemctl start healthcheck.timer

echo "✅ Systemd timer installed (runs every 6 hours)."
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ Installation complete!                           ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Run now:     sudo python3 ${APP_DIR}/healthcheck.py"
echo "║  Reports:     ${HEALTHCHECK_DIR}/"
echo "║  Latest:      ${HEALTHCHECK_DIR}/latest.html"
echo "║  Timer status: systemctl status healthcheck.timer"
echo "║  View logs:   journalctl -u healthcheck.service -f"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
