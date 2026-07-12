<div align="center">

# 🔍 Linux Server Health Check & Virus Scanner

**A Python tool that runs a full system audit + ClamAV virus scan and saves a beautiful HTML report to `/healthcheck/`**

[![Python](https://img.shields.io/badge/Python-3.6%2B-blue?style=flat-square&logo=python)](https://python.org)
[![ClamAV](https://img.shields.io/badge/ClamAV-Powered-red?style=flat-square)](https://www.clamav.net/)
[![Platform](https://img.shields.io/badge/Platform-Linux-orange?style=flat-square&logo=linux)](https://kernel.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Root](https://img.shields.io/badge/Requires-sudo-critical?style=flat-square)]()

</div>

---

## 📸 Screenshot

![Health Check Dashboard](screenshot.png)

---

## ✨ Features

| Category | What's Collected |
|---|---|
| 🖥️ **System** | OS, kernel, hostname, architecture, uptime |
| ⚡ **CPU** | Usage %, load average (1/5/15m), top processes |
| 🧠 **Memory** | RAM usage, swap usage, cached/buffered |
| 💾 **Disk** | All mount points, inode usage, large files (>100MB) |
| 🌐 **Network** | Interfaces, IPs, open ports, active connections |
| ⚙️ **Processes** | Total count, zombie detection, top memory users |
| 🔧 **Services** | SSH, cron, nginx, docker, fail2ban, firewall, etc. |
| 🔒 **Security** | Failed SSH attempts, world-writable files, active sessions |
| 🛡️ **Virus Scan** | Full ClamAV scan with infected file names + threat types |

**Output formats:** Timestamped HTML dashboard + JSON (machine-readable)

---

## 📁 Project Structure

```
healthcheck_app/
├── healthcheck.py     ← Main script — run this
├── syshealth.py       ← System metrics collector
├── scanner.py         ← ClamAV virus scanner
├── reporter.py        ← HTML + JSON report generator
├── install.sh         ← One-shot setup script
├── requirements.txt   ← No pip packages needed
└── README.md
```

---

## 🚀 Quick Start

### Step 1 — Copy files to your Linux server

```bash
scp -r healthcheck_app/ user@your-server:/opt/healthcheck_app/
```

### Step 2 — Install ClamAV and enable auto-scheduling

```bash
cd /opt/healthcheck_app
sudo bash install.sh
```

> `install.sh` will:
> - Install **ClamAV** via `apt` / `yum`
> - Update the virus signature database with `freshclam`
> - Create the `/healthcheck/` output directory
> - Register a **systemd timer** to run every 6 hours automatically

### Step 3 — Run manually

```bash
sudo python3 /opt/healthcheck_app/healthcheck.py
```

### Step 4 — Open the report

```
/healthcheck/latest.html                            ← Always the newest
/healthcheck/healthcheck_2026-07-12_10-10-00.html  ← Timestamped copy
/healthcheck/healthcheck_2026-07-12_10-10-00.json  ← JSON data
```

---

## ⚙️ CLI Options

```bash
sudo python3 healthcheck.py [OPTIONS]

  -o, --output-dir PATH       Save reports here (default: /healthcheck)
  -d, --scan-dirs DIR [...]   Directories to virus-scan
  -s, --skip-virus-scan       Skip ClamAV scan (faster, no AV check)
  -m, --max-filesize MB       Max file size to scan in MB (default: 100)
      --help                  Show help
```

**Examples:**

```bash
# Scan only web directories
sudo python3 healthcheck.py --scan-dirs /var/www /home /tmp

# Save to a custom path
sudo python3 healthcheck.py --output-dir /var/reports

# Quick health check without virus scan
sudo python3 healthcheck.py --skip-virus-scan

# Scan larger files too
sudo python3 healthcheck.py --max-filesize 500
```

---

## 🕒 Automatic Scheduling (systemd)

After running `install.sh`, the timer is already active:

```bash
# Check timer status
systemctl status healthcheck.timer

# View logs in real time
journalctl -u healthcheck.service -f

# Trigger a run right now
systemctl start healthcheck.service

# Change schedule (edit and reload)
nano /etc/systemd/system/healthcheck.timer
systemctl daemon-reload && systemctl restart healthcheck.timer
```

### Or use cron instead:

```bash
# Run daily at 3:00 AM
echo "0 3 * * * root python3 /opt/healthcheck_app/healthcheck.py" | sudo tee -a /etc/crontab
```

---

## 🔔 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — no infections found |
| `1` | Script error |
| `2` | **Virus / malware detected** |

Use in shell scripts or alerting pipelines:

```bash
sudo python3 healthcheck.py
STATUS=$?

if [ "$STATUS" -eq 2 ]; then
  echo "🔴 VIRUS DETECTED on $(hostname)!" | mail -s "ALERT" admin@example.com
elif [ "$STATUS" -eq 0 ]; then
  echo "✅ Server clean."
fi
```

---

## 📧 Email Reports (Optional)

```bash
# Send HTML report by email after each run
sudo python3 healthcheck.py && \
  mail -s "Health Report - $(hostname) - $(date +%Y-%m-%d)" \
  admin@example.com < /healthcheck/latest.html
```

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Linux (Ubuntu, Debian, CentOS, RHEL, Arch) |
| **Python** | 3.6 or newer |
| **ClamAV** | Auto-installed by `install.sh` |
| **Privileges** | `sudo` / root (for full system access) |
| **pip packages** | ❌ None — uses only Python stdlib + system tools |

**System tools used** (all standard on Linux):
`ps`, `df`, `ip`, `ss`, `systemctl`, `who`, `last`, `find`, `grep`, `uptime`, `clamscan`, `freshclam`

---

## 🗂️ Sample JSON Output

```json
{
  "meta": {
    "generated_at": "2026-07-12_10-10-00",
    "hostname": "myserver.example.com"
  },
  "health": {
    "cpu": { "usage_pct": 12.4, "cores": 8, "load_1m": 0.52 },
    "memory": { "total_mb": 8192, "used_mb": 2048, "usage_pct": 25.0 },
    "disk": { "partitions": [ { "mountpoint": "/", "use_pct": "34%" } ] }
  },
  "virus_scan": {
    "infected": 0,
    "scanned": 142803,
    "scan_time_s": 187.3,
    "version": "ClamAV 1.2.1"
  }
}
```

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

<div align="center">

Made with ❤️ for Linux sysadmins &nbsp;|&nbsp; **No dependencies. No bloat. Just Python.**

</div>
