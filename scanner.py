"""
scanner.py — Virus Scanner Module
Uses ClamAV (clamscan) to scan directories for malware and viruses.
"""

import subprocess
import shutil
import datetime
import re
from pathlib import Path


DEFAULT_SCAN_DIRS = ["/home", "/tmp", "/var/tmp", "/etc", "/usr/local/bin"]
EXCLUDE_DIRS = [
    "/proc", "/sys", "/dev", "/run",
    "/healthcheck", "/healthcheck_app",
]


def _is_clamav_installed():
    """Check if clamscan is available on the system."""
    return shutil.which("clamscan") is not None


def _get_clamav_version():
    """Return ClamAV version string."""
    try:
        result = subprocess.run(
            ["clamscan", "--version"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return f"Unknown ({e})"


def _get_db_info():
    """Return virus database info."""
    try:
        result = subprocess.run(
            ["sigtool", "--info", "/var/lib/clamav/main.cvd"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "Build time" in line or "Signatures" in line:
                return result.stdout.strip()
    except Exception:
        pass
    # fallback: check freshclam log
    try:
        log_path = Path("/var/log/clamav/freshclam.log")
        if log_path.exists():
            lines = log_path.read_text().splitlines()
            for line in reversed(lines):
                if "daily" in line.lower() or "main" in line.lower():
                    return line.strip()
    except Exception:
        pass
    return "N/A"


def scan_directory(scan_dirs=None, max_filesize_mb=100, callback=None):
    """
    Scan directories with ClamAV.

    Args:
        scan_dirs: list of paths to scan (defaults to DEFAULT_SCAN_DIRS)
        max_filesize_mb: skip files larger than this (MB)
        callback: optional callable(msg) for progress updates

    Returns:
        dict with scan results
    """
    if not _is_clamav_installed():
        return {
            "available": False,
            "error": "ClamAV (clamscan) is not installed. Run: sudo apt-get install clamav",
            "infected_files": [],
            "scanned": 0,
            "infected": 0,
            "errors": 0,
            "scan_time_s": 0,
            "version": "N/A",
            "db_info": "N/A",
            "scan_dirs": [],
            "started_at": datetime.datetime.now().isoformat(),
            "finished_at": datetime.datetime.now().isoformat(),
        }

    if scan_dirs is None:
        scan_dirs = DEFAULT_SCAN_DIRS

    # Filter to existing dirs only
    valid_dirs = [d for d in scan_dirs if Path(d).exists()]

    version = _get_clamav_version()
    db_info = _get_db_info()

    # Build exclude args
    exclude_args = []
    for ex in EXCLUDE_DIRS:
        exclude_args += ["--exclude-dir", ex]

    cmd = [
        "clamscan",
        "--recursive",
        "--infected",                     # only print infected files
        "--no-summary",                   # we parse summary separately
        f"--max-filesize={max_filesize_mb}M",
        f"--max-scansize={max_filesize_mb}M",
        "--stdout",
        *exclude_args,
        *valid_dirs,
    ]

    # Run with summary — separate call for stats
    cmd_with_summary = [
        "clamscan",
        "--recursive",
        f"--max-filesize={max_filesize_mb}M",
        f"--max-scansize={max_filesize_mb}M",
        "--stdout",
        *exclude_args,
        *valid_dirs,
    ]

    if callback:
        callback(f"Starting ClamAV scan on: {', '.join(valid_dirs)}")

    started_at = datetime.datetime.now()

    infected_files = []
    scanned = 0
    infected = 0
    errors = 0
    raw_output = []

    try:
        proc = subprocess.Popen(
            cmd_with_summary,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        for line in proc.stdout:
            line = line.rstrip()
            raw_output.append(line)

            # Detect infected files
            if "FOUND" in line:
                infected_files.append({
                    "path": line.split(":")[0].strip(),
                    "threat": re.search(r": (.+) FOUND", line).group(1) if re.search(r": (.+) FOUND", line) else "Unknown",
                    "raw": line,
                })
                if callback:
                    callback(f"⚠️  INFECTED: {line}")

            # Parse summary lines
            elif "Scanned files:" in line:
                m = re.search(r"(\d+)", line)
                scanned = int(m.group(1)) if m else 0
            elif "Infected files:" in line:
                m = re.search(r"(\d+)", line)
                infected = int(m.group(1)) if m else 0
            elif "Scan errors:" in line or "Errors:" in line:
                m = re.search(r"(\d+)", line)
                errors = int(m.group(1)) if m else 0
            else:
                if callback and line:
                    # Show progress for every 1000 files
                    if "Scanning" in line:
                        callback(f"  Scanning: {line[:80]}")

        proc.wait()

    except Exception as e:
        return {
            "available": True,
            "error": str(e),
            "infected_files": [],
            "scanned": 0,
            "infected": 0,
            "errors": 0,
            "scan_time_s": 0,
            "version": version,
            "db_info": db_info,
            "scan_dirs": valid_dirs,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.datetime.now().isoformat(),
        }

    finished_at = datetime.datetime.now()
    scan_time = (finished_at - started_at).total_seconds()

    if callback:
        status = "✅ CLEAN" if infected == 0 else f"🔴 {infected} INFECTED FILE(S) FOUND"
        callback(f"Scan complete: {status} | Scanned: {scanned} | Time: {scan_time:.1f}s")

    return {
        "available": True,
        "error": None,
        "infected_files": infected_files,
        "scanned": scanned,
        "infected": infected,
        "errors": errors,
        "scan_time_s": round(scan_time, 1),
        "version": version,
        "db_info": db_info,
        "scan_dirs": valid_dirs,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "raw_output_tail": raw_output[-30:],  # last 30 lines for debug
    }
