"""
syshealth.py — System Health Metrics Collector
Collects CPU, memory, disk, network, processes, and security info.
"""

import os
import re
import socket
import subprocess
import platform
import datetime
import shutil
from pathlib import Path


def _run(cmd, timeout=30):
    """Run a shell command safely and return stdout."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    except Exception as e:
        return "", str(e)


def _read_file(path, default="N/A"):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


# ─────────────────────────── OS / SYSTEM INFO ───────────────────────────────

def get_os_info():
    uname = platform.uname()
    uptime_raw, _ = _run("uptime -p")
    uptime_since, _ = _run("uptime -s")
    hostname = socket.getfqdn()

    # OS release info
    os_release = {}
    for line in _read_file("/etc/os-release", "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            os_release[k.strip()] = v.strip().strip('"')

    return {
        "hostname": hostname,
        "os": os_release.get("PRETTY_NAME", platform.platform()),
        "kernel": uname.release,
        "architecture": uname.machine,
        "uptime": uptime_raw or "N/A",
        "uptime_since": uptime_since or "N/A",
        "python_version": platform.python_version(),
        "timestamp": datetime.datetime.now().isoformat(),
    }


# ─────────────────────────── CPU ────────────────────────────────────────────

def get_cpu_info():
    # Load averages
    load_avg = os.getloadavg()

    # CPU count
    cpu_count = os.cpu_count() or 1

    # Usage via /proc/stat (two-sample delta)
    def _read_stat():
        try:
            with open("/proc/stat") as f:
                line = f.readline()
            vals = list(map(int, line.split()[1:]))
            idle = vals[3]
            total = sum(vals)
            return idle, total
        except Exception:
            return None, None

    idle1, total1 = _read_stat()
    import time; time.sleep(0.5)
    idle2, total2 = _read_stat()

    if idle1 is not None and total2 != total1:
        usage_pct = round(100.0 * (1 - (idle2 - idle1) / (total2 - total1)), 2)
    else:
        usage_pct = "N/A"

    # CPU model
    cpu_model = "N/A"
    for line in _read_file("/proc/cpuinfo", "").splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break

    # CPU frequency
    freq_raw = _read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", None)
    freq_mhz = round(int(freq_raw) / 1000, 1) if freq_raw else "N/A"

    # Top CPU processes
    top_cpu, _ = _run("ps aux --sort=-%cpu | head -11")
    top_cpu_lines = top_cpu.splitlines()[1:] if top_cpu else []
    top_processes = []
    for line in top_cpu_lines:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            top_processes.append({
                "user": parts[0], "pid": parts[1],
                "cpu": parts[2], "mem": parts[3],
                "command": parts[10][:60],
            })

    return {
        "model": cpu_model,
        "cores": cpu_count,
        "usage_pct": usage_pct,
        "load_1m": round(load_avg[0], 2),
        "load_5m": round(load_avg[1], 2),
        "load_15m": round(load_avg[2], 2),
        "freq_mhz": freq_mhz,
        "top_processes": top_processes[:10],
    }


# ─────────────────────────── MEMORY ─────────────────────────────────────────

def get_memory_info():
    meminfo = {}
    for line in _read_file("/proc/meminfo", "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meminfo[k.strip()] = v.strip()

    def kb(key):
        try:
            return int(meminfo.get(key, "0 kB").split()[0])
        except ValueError:
            return 0

    total_kb = kb("MemTotal")
    available_kb = kb("MemAvailable")
    free_kb = kb("MemFree")
    buffers_kb = kb("Buffers")
    cached_kb = kb("Cached")
    swap_total_kb = kb("SwapTotal")
    swap_free_kb = kb("SwapFree")

    used_kb = total_kb - available_kb
    swap_used_kb = swap_total_kb - swap_free_kb

    def mb(kb_val):
        return round(kb_val / 1024, 1)

    def pct(used, total):
        return round(100.0 * used / total, 1) if total > 0 else 0.0

    return {
        "total_mb": mb(total_kb),
        "used_mb": mb(used_kb),
        "free_mb": mb(free_kb),
        "available_mb": mb(available_kb),
        "buffers_mb": mb(buffers_kb),
        "cached_mb": mb(cached_kb),
        "usage_pct": pct(used_kb, total_kb),
        "swap_total_mb": mb(swap_total_kb),
        "swap_used_mb": mb(swap_used_kb),
        "swap_usage_pct": pct(swap_used_kb, swap_total_kb),
    }


# ─────────────────────────── DISK ───────────────────────────────────────────

def get_disk_info():
    partitions = []
    df_out, _ = _run("df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs -x squashfs")
    lines = df_out.splitlines()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 6:
            partitions.append({
                "device": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_pct": parts[4],
                "mountpoint": parts[5],
            })

    # Inode usage
    inodes = []
    df_inode, _ = _run("df -i --output=source,itotal,iused,iavail,ipcent,target -x tmpfs -x devtmpfs -x squashfs")
    for line in df_inode.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            inodes.append({
                "device": parts[0],
                "total": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_pct": parts[4],
                "mountpoint": parts[5],
            })

    # Largest files (top 10)
    large_files = []
    lf_out, _ = _run("find / -xdev -type f -size +100M -printf '%s %p\n' 2>/dev/null | sort -rn | head -10", timeout=60)
    for line in lf_out.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            size_bytes = int(parts[0])
            large_files.append({
                "path": parts[1],
                "size_mb": round(size_bytes / 1024 / 1024, 1),
            })

    return {
        "partitions": partitions,
        "inodes": inodes,
        "large_files": large_files,
    }


# ─────────────────────────── NETWORK ────────────────────────────────────────

def get_network_info():
    interfaces = []
    ip_out, _ = _run("ip -s link show")

    # Parse /proc/net/dev for stats
    net_dev = _read_file("/proc/net/dev", "")
    for line in net_dev.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 10:
            iface = parts[0].rstrip(":")
            if iface == "lo":
                continue
            interfaces.append({
                "name": iface,
                "rx_mb": round(int(parts[1]) / 1024 / 1024, 2),
                "tx_mb": round(int(parts[9]) / 1024 / 1024, 2),
                "rx_errors": parts[3],
                "tx_errors": parts[11],
            })

    # IP addresses
    ip_addr_out, _ = _run("ip -4 addr show")
    ip_map = {}
    current_iface = None
    for line in ip_addr_out.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            parts = line.split()
            if len(parts) >= 2:
                current_iface = parts[1].rstrip(":")
        elif line.startswith("inet ") and current_iface:
            ip_map[current_iface] = line.split()[1]

    for iface in interfaces:
        iface["ip"] = ip_map.get(iface["name"], "N/A")

    # Open ports
    open_ports = []
    ss_out, _ = _run("ss -tlnp")
    for line in ss_out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            open_ports.append({
                "state": parts[0],
                "local": parts[3],
                "process": parts[6] if len(parts) > 6 else "N/A",
            })

    # Active connections count
    conn_count_out, _ = _run("ss -tun | grep -c ESTAB")
    try:
        conn_count = int(conn_count_out)
    except ValueError:
        conn_count = 0

    return {
        "interfaces": interfaces,
        "open_ports": open_ports[:20],
        "established_connections": conn_count,
    }


# ─────────────────────────── PROCESSES ──────────────────────────────────────

def get_process_info():
    # Total process count
    proc_count_out, _ = _run("ps aux | wc -l")
    try:
        total_procs = int(proc_count_out) - 1
    except ValueError:
        total_procs = 0

    # Zombie processes
    zombie_out, _ = _run("ps aux | awk '$8==\"Z\"'")
    zombies = [line for line in zombie_out.splitlines() if line.strip()]

    # Top memory processes
    top_mem, _ = _run("ps aux --sort=-%mem | head -11")
    top_mem_procs = []
    for line in top_mem.splitlines()[1:]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            top_mem_procs.append({
                "user": parts[0], "pid": parts[1],
                "cpu": parts[2], "mem": parts[3],
                "command": parts[10][:60],
            })

    return {
        "total": total_procs,
        "zombies": len(zombies),
        "zombie_list": zombies[:5],
        "top_memory": top_mem_procs[:10],
    }


# ─────────────────────────── SERVICES ───────────────────────────────────────

def get_service_info():
    services_to_check = [
        "ssh", "sshd", "cron", "crond", "ufw", "firewalld",
        "fail2ban", "nginx", "apache2", "httpd", "mysql",
        "mariadb", "postgresql", "docker", "systemd-journald",
    ]

    service_status = []
    for svc in services_to_check:
        out, _ = _run(f"systemctl is-active {svc} 2>/dev/null")
        if out:  # only include if systemctl responded
            service_status.append({
                "name": svc,
                "status": out.strip(),
                "active": out.strip() == "active",
            })

    # Failed units
    failed_out, _ = _run("systemctl list-units --failed --no-pager --plain 2>/dev/null | head -20")
    failed_units = [l for l in failed_out.splitlines() if "failed" in l.lower()]

    return {
        "checked": service_status,
        "failed_units": failed_units,
    }


# ─────────────────────────── SECURITY ───────────────────────────────────────

def get_security_info():
    # Last failed SSH login attempts
    failed_logins, _ = _run(
        "grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -20 || "
        "grep 'Failed password' /var/log/secure 2>/dev/null | tail -20"
    )
    failed_login_lines = [l for l in failed_logins.splitlines() if l.strip()]

    # Last successful logins
    last_logins, _ = _run("last -n 10 --time-format iso 2>/dev/null || last -n 10")
    last_login_lines = [l for l in last_logins.splitlines() if l.strip()]

    # Currently logged-in users
    who_out, _ = _run("who")
    logged_in = [l for l in who_out.splitlines() if l.strip()]

    # Check for world-writable files in sensitive dirs (quick check)
    world_writable, _ = _run(
        "find /etc /usr/bin /usr/sbin -xdev -type f -perm -o+w 2>/dev/null | head -10",
        timeout=30,
    )
    ww_files = [l for l in world_writable.splitlines() if l.strip()]

    # Sudoers
    sudoers_out, _ = _run("cat /etc/sudoers 2>/dev/null | grep -v '^#' | grep -v '^$' | head -20")

    # Check SELinux / AppArmor status
    selinux, _ = _run("getenforce 2>/dev/null")
    apparmor, _ = _run("aa-status --brief 2>/dev/null || apparmor_status --brief 2>/dev/null")

    # Pending security updates
    updates, _ = _run(
        "apt-get -s upgrade 2>/dev/null | grep -i security | wc -l || "
        "yum check-update --security 2>/dev/null | grep -c 'security' || echo 'N/A'"
    )

    return {
        "failed_logins_last20": failed_login_lines[:10],
        "last_logins": last_login_lines[:10],
        "logged_in_users": logged_in,
        "world_writable_sensitive": ww_files,
        "selinux_status": selinux or "N/A",
        "apparmor_status": apparmor.splitlines()[0] if apparmor else "N/A",
        "pending_security_updates": updates.strip() if updates.strip() else "N/A",
        "sudoers_excerpt": sudoers_out.splitlines()[:10],
    }


# ─────────────────────────── AGGREGATE ──────────────────────────────────────

def collect_all():
    """Collect all system health metrics and return as a dict."""
    print("  [*] Collecting OS info...")
    os_info = get_os_info()

    print("  [*] Collecting CPU info...")
    cpu_info = get_cpu_info()

    print("  [*] Collecting memory info...")
    mem_info = get_memory_info()

    print("  [*] Collecting disk info...")
    disk_info = get_disk_info()

    print("  [*] Collecting network info...")
    net_info = get_network_info()

    print("  [*] Collecting process info...")
    proc_info = get_process_info()

    print("  [*] Collecting service info...")
    svc_info = get_service_info()

    print("  [*] Collecting security info...")
    sec_info = get_security_info()

    return {
        "os": os_info,
        "cpu": cpu_info,
        "memory": mem_info,
        "disk": disk_info,
        "network": net_info,
        "processes": proc_info,
        "services": svc_info,
        "security": sec_info,
    }
