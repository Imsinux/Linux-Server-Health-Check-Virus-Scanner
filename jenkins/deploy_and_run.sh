#!/bin/bash
# jenkins/deploy_and_run.sh
# ─────────────────────────────────────────────────────────────────────────────
# Deploys healthcheck_app to a remote server and runs the health check.
# Called by Jenkinsfile for each server.
#
# Required env vars (injected by Jenkins withCredentials):
#   REMOTE_HOST       — server IP or hostname
#   REMOTE_USER       — SSH username
#   REMOTE_PASS       — SSH password (from Jenkins Credentials Store)
#   REMOTE_LABEL      — human-readable server label
#   SCAN_DIRS         — space-separated dirs to scan
#   APP_SRC           — local path to healthcheck_app/ (WORKSPACE)
#   REPORT_DEST       — local dir to save downloaded reports
#   ALERT_EMAIL       — email to notify on virus detection (optional)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REMOTE_APP_DIR="/opt/healthcheck_app"
REMOTE_OUTPUT_DIR="/healthcheck"

log() { echo "[$(date '+%H:%M:%S')] [$REMOTE_LABEL] $1"; }
log_warn() { echo "[$(date '+%H:%M:%S')] [$REMOTE_LABEL] ⚠️  $1" >&2; }
log_ok()   { echo "[$(date '+%H:%M:%S')] [$REMOTE_LABEL] ✅ $1"; }
log_err()  { echo "[$(date '+%H:%M:%S')] [$REMOTE_LABEL] ❌ $1" >&2; }

# ── SSH / SCP helpers ─────────────────────────────────────────────────────────
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=no"

ssh_run() {
    sshpass -p "$REMOTE_PASS" ssh $SSH_OPTS "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

scp_put() {
    # $1 = local source, $2 = remote destination
    sshpass -p "$REMOTE_PASS" scp -r $SSH_OPTS "$1" "${REMOTE_USER}@${REMOTE_HOST}:$2"
}

scp_get() {
    # $1 = remote source, $2 = local destination
    sshpass -p "$REMOTE_PASS" scp -r $SSH_OPTS "${REMOTE_USER}@${REMOTE_HOST}:$1" "$2"
}

# ── Step 1: Connectivity check ────────────────────────────────────────────────
log "Testing SSH connectivity..."
if ! ssh_run "echo connected" &>/dev/null; then
    log_err "Cannot connect to ${REMOTE_HOST}. Check host/credentials."
    exit 1
fi
log_ok "SSH connection OK."

# ── Step 2: Deploy app files ──────────────────────────────────────────────────
log "Deploying healthcheck_app to ${REMOTE_HOST}:${REMOTE_APP_DIR} ..."
ssh_run "mkdir -p ${REMOTE_APP_DIR}"
scp_put "${APP_SRC}/healthcheck.py" "${REMOTE_APP_DIR}/"
scp_put "${APP_SRC}/syshealth.py"   "${REMOTE_APP_DIR}/"
scp_put "${APP_SRC}/scanner.py"     "${REMOTE_APP_DIR}/"
scp_put "${APP_SRC}/reporter.py"    "${REMOTE_APP_DIR}/"
log_ok "Files deployed."

# ── Step 3: Ensure ClamAV is installed ────────────────────────────────────────
log "Checking ClamAV installation..."
CLAM_INSTALLED=$(ssh_run "command -v clamscan && echo yes || echo no")
if [ "$CLAM_INSTALLED" = "no" ]; then
    log "ClamAV not found — installing..."
    ssh_run "
        if command -v apt-get &>/dev/null; then
            apt-get update -qq && apt-get install -y -q clamav clamav-freshclam
        elif command -v yum &>/dev/null; then
            yum install -y -q clamav clamav-update
        elif command -v dnf &>/dev/null; then
            dnf install -y -q clamav clamav-update
        else
            echo 'Cannot install ClamAV: no known package manager' >&2
            exit 1
        fi
    "
    log_ok "ClamAV installed."
else
    log_ok "ClamAV already present."
fi

# ── Step 4: Update virus DB ────────────────────────────────────────────────────
log "Updating ClamAV virus database..."
ssh_run "
    systemctl stop clamav-freshclam 2>/dev/null || true
    freshclam --quiet 2>/dev/null || echo 'freshclam warning (non-fatal)'
    systemctl start clamav-freshclam 2>/dev/null || true
"
log_ok "Virus database updated."

# ── Step 5: Create output directory ───────────────────────────────────────────
ssh_run "mkdir -p ${REMOTE_OUTPUT_DIR} && chmod 755 ${REMOTE_OUTPUT_DIR}"

# ── Step 6: Run the health check ──────────────────────────────────────────────
log "Running health check + virus scan on ${REMOTE_HOST}..."
log "Scan dirs: ${SCAN_DIRS}"

SCAN_ARGS=""
if [ -n "${SCAN_DIRS:-}" ]; then
    SCAN_ARGS="--scan-dirs ${SCAN_DIRS}"
fi

EXIT_CODE=0
ssh_run "python3 ${REMOTE_APP_DIR}/healthcheck.py \
    --output-dir ${REMOTE_OUTPUT_DIR} \
    ${SCAN_ARGS}" || EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    log_ok "Health check complete — server is CLEAN."
elif [ "$EXIT_CODE" -eq 2 ]; then
    log_warn "VIRUS DETECTED on ${REMOTE_LABEL} (${REMOTE_HOST})!"
else
    log_err "Health check script failed with exit code ${EXIT_CODE}."
    exit "$EXIT_CODE"
fi

# ── Step 7: Collect reports back to Jenkins ───────────────────────────────────
log "Downloading reports from ${REMOTE_HOST}..."
mkdir -p "${REPORT_DEST}"

# Download only the latest HTML report
scp_get "${REMOTE_OUTPUT_DIR}/latest.html" \
    "${REPORT_DEST}/${REMOTE_LABEL}_latest.html" || log_warn "Could not download latest.html"

# Download only the latest JSON report
scp_get "${REMOTE_OUTPUT_DIR}/latest.json" \
    "${REPORT_DEST}/${REMOTE_LABEL}_latest.json" || log_warn "Could not download latest.json"

# Clean up old timestamped files on the remote server — keep only the newest 1
ssh_run "
    cd ${REMOTE_OUTPUT_DIR} 2>/dev/null || exit 0
    ls -t healthcheck_*.html 2>/dev/null | tail -n +2 | xargs rm -f
    ls -t healthcheck_*.json 2>/dev/null | tail -n +2 | xargs rm -f
" || true

log_ok "Reports saved to ${REPORT_DEST}/"

# ── Step 8: Write status file for Jenkins summary ────────────────────────────
STATUS="CLEAN"
[ "$EXIT_CODE" -eq 2 ] && STATUS="VIRUS_FOUND"

cat > "${REPORT_DEST}/${REMOTE_LABEL}_status.txt" <<EOF
SERVER=${REMOTE_LABEL}
HOST=${REMOTE_HOST}
STATUS=${STATUS}
EXIT_CODE=${EXIT_CODE}
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
EOF

log_ok "Done. Status: ${STATUS}"

# Return exit code 2 to caller if virus found (Jenkins handles it)
exit "$EXIT_CODE"
