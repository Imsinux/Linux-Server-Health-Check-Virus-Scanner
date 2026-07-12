#!/usr/bin/env python3
"""
healthcheck.py — Linux Server Health Check & Virus Scanner
============================================================
Runs a full system health check and ClamAV virus scan,
then saves a beautiful HTML + JSON report to /healthcheck/.

Usage:
    sudo python3 healthcheck.py [OPTIONS]

Options:
    --output-dir PATH       Output directory (default: /healthcheck)
    --scan-dirs DIR [...]   Directories to virus-scan
    --skip-virus-scan       Skip the ClamAV virus scan
    --help                  Show this help message
"""

import sys
import os
import argparse
import datetime

# ANSI colors for terminal output
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
PURPLE = "\033[95m"


def banner():
    print(f"""
{PURPLE}{BOLD}
╔══════════════════════════════════════════════════════╗
║     🔍  Linux Server Health Check & Virus Scanner    ║
║          healthcheck.py  —  Full System Audit        ║
╚══════════════════════════════════════════════════════╝
{RESET}""")


def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    colors = {"INFO": CYAN, "OK": GREEN, "WARN": YELLOW, "ERROR": RED, "SECTION": PURPLE + BOLD}
    color = colors.get(level, RESET)
    print(f"{color}[{ts}] [{level}] {msg}{RESET}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Linux Server Health Check & Virus Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="/healthcheck",
        help="Directory to save reports (default: /healthcheck)",
    )
    parser.add_argument(
        "--scan-dirs", "-d",
        nargs="+",
        default=None,
        help="Directories to scan for viruses (default: /home /tmp /var/tmp /etc /usr/local/bin)",
    )
    parser.add_argument(
        "--skip-virus-scan", "-s",
        action="store_true",
        help="Skip the ClamAV virus scan (faster, but no malware detection)",
    )
    parser.add_argument(
        "--max-filesize", "-m",
        type=int,
        default=100,
        help="Max file size in MB to scan (default: 100)",
    )
    return parser.parse_args()


def check_root():
    if os.geteuid() != 0:
        log("WARNING: Not running as root. Some checks may be incomplete.", "WARN")
        log("For full access, run: sudo python3 healthcheck.py", "WARN")
        print()


def main():
    banner()
    args = parse_args()
    check_root()

    start_time = datetime.datetime.now()
    log(f"Starting health check at {start_time.strftime('%Y-%m-%d %H:%M:%S')}", "SECTION")
    log(f"Output directory: {args.output_dir}", "INFO")
    print()

    # ── Step 1: System Health ───────────────────────────────────────────────
    log("═══ STEP 1/3: Collecting System Health Metrics ═══", "SECTION")
    try:
        import syshealth
        health_data = syshealth.collect_all()
        log("System health metrics collected successfully.", "OK")
    except Exception as e:
        log(f"Failed to collect system health metrics: {e}", "ERROR")
        sys.exit(1)
    print()

    # ── Step 2: Virus Scan ─────────────────────────────────────────────────
    log("═══ STEP 2/3: Virus Scanning with ClamAV ═══", "SECTION")
    scan_data = {}
    if args.skip_virus_scan:
        log("Virus scan skipped (--skip-virus-scan flag set).", "WARN")
        scan_data = {
            "available": False,
            "error": "Scan skipped by user (--skip-virus-scan)",
            "infected_files": [], "scanned": 0, "infected": 0, "errors": 0,
            "scan_time_s": 0, "version": "N/A", "db_info": "N/A",
            "scan_dirs": [], "started_at": "N/A", "finished_at": "N/A",
        }
    else:
        try:
            import scanner

            def progress(msg):
                log(msg, "INFO")

            scan_data = scanner.scan_directory(
                scan_dirs=args.scan_dirs,
                max_filesize_mb=args.max_filesize,
                callback=progress,
            )

            if not scan_data.get("available"):
                log(scan_data.get("error", "ClamAV unavailable"), "WARN")
                log("Install ClamAV: sudo apt-get install clamav clamav-daemon", "WARN")
                log("Then update DB: sudo freshclam", "WARN")
            elif scan_data.get("infected", 0) > 0:
                log(f"🔴 ALERT: {scan_data['infected']} infected file(s) found!", "ERROR")
                for inf in scan_data.get("infected_files", []):
                    log(f"  INFECTED: {inf['path']} — {inf['threat']}", "ERROR")
            else:
                log(f"✅ Scan clean: {scan_data.get('scanned',0):,} files scanned, 0 infected.", "OK")
        except Exception as e:
            log(f"Virus scan error: {e}", "ERROR")
            scan_data = {
                "available": False, "error": str(e),
                "infected_files": [], "scanned": 0, "infected": 0, "errors": 0,
                "scan_time_s": 0, "version": "N/A", "db_info": "N/A",
                "scan_dirs": [], "started_at": "N/A", "finished_at": "N/A",
            }
    print()

    # ── Step 3: Generate Report ────────────────────────────────────────────
    log("═══ STEP 3/3: Generating Report ═══", "SECTION")
    try:
        import reporter
        paths = reporter.generate_report(
            health_data=health_data,
            scan_data=scan_data,
            output_dir=args.output_dir,
        )
        log("Report generated successfully!", "OK")
        log(f"  📄 HTML:   {paths['html']}", "OK")
        log(f"  📊 JSON:   {paths['json']}", "OK")
        log(f"  🔗 Latest: {paths['latest']}", "OK")
    except Exception as e:
        log(f"Failed to generate report: {e}", "ERROR")
        sys.exit(1)

    # ── Summary ────────────────────────────────────────────────────────────
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    print()
    log(f"═══ DONE in {elapsed:.1f}s ═══", "SECTION")
    log(f"Open report: {paths['html']}", "OK")
    log(f"Or view latest: {paths['latest']}", "OK")

    # Exit code: 1 if infections found
    if scan_data.get("infected", 0) > 0:
        sys.exit(2)  # 2 = virus found
    sys.exit(0)


if __name__ == "__main__":
    main()
