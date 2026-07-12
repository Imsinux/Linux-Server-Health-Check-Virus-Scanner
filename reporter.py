"""
reporter.py — HTML & JSON Report Generator
Generates a beautiful, color-coded health report and saves to /healthcheck/.
"""

import json
import datetime
import os
from pathlib import Path


OUTPUT_DIR = "/healthcheck"


# ─────────────────────────── HELPERS ────────────────────────────────────────

def _status_badge(ok, ok_label="OK", fail_label="WARN"):
    cls = "badge-ok" if ok else "badge-warn"
    label = ok_label if ok else fail_label
    return f'<span class="badge {cls}">{label}</span>'


def _pct_bar(pct, warn=70, danger=90):
    try:
        val = float(str(pct).replace("%", ""))
    except Exception:
        return f'<span class="na">N/A</span>'
    color = "#4ade80" if val < warn else ("#facc15" if val < danger else "#f87171")
    return (
        f'<div class="bar-wrap" title="{val}%">'
        f'<div class="bar-fill" style="width:{min(val,100)}%;background:{color}"></div>'
        f'<span class="bar-label">{val}%</span>'
        f'</div>'
    )


def _table(headers, rows, empty_msg="No data"):
    if not rows:
        return f'<p class="empty">{empty_msg}</p>'
    cols = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{c}</td>" for c in row)
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{cols}</tr></thead><tbody>{body}</tbody></table>"


# ─────────────────────────── SECTIONS ───────────────────────────────────────

def _section_os(data):
    d = data["os"]
    rows = [
        ("Hostname", d["hostname"]),
        ("Operating System", d["os"]),
        ("Kernel", d["kernel"]),
        ("Architecture", d["architecture"]),
        ("Uptime", d["uptime"]),
        ("Uptime Since", d["uptime_since"]),
        ("Python Version", d["python_version"]),
        ("Report Generated", d["timestamp"]),
    ]
    inner = "".join(f"<tr><td class='key'>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f"""
    <section id="os">
      <h2>🖥️ System Overview</h2>
      <table class="info-table"><tbody>{inner}</tbody></table>
    </section>"""


def _section_cpu(data):
    c = data["cpu"]
    usage = c["usage_pct"]
    try:
        usage_f = float(usage)
        ok = usage_f < 80
    except Exception:
        ok = True

    procs_rows = [
        (p["user"], p["pid"], p["cpu"] + "%", p["mem"] + "%", p["command"])
        for p in c.get("top_processes", [])
    ]

    return f"""
    <section id="cpu">
      <h2>⚡ CPU</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Usage</div>
          <div class="metric-value">{usage}%</div>
          {_pct_bar(usage, 70, 90)}
          {_status_badge(ok, "NORMAL", "HIGH")}
        </div>
        <div class="metric-card">
          <div class="metric-label">Cores</div>
          <div class="metric-value">{c["cores"]}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Freq</div>
          <div class="metric-value">{c["freq_mhz"]} MHz</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Load (1/5/15m)</div>
          <div class="metric-value">{c["load_1m"]} / {c["load_5m"]} / {c["load_15m"]}</div>
        </div>
      </div>
      <h3>Top CPU Processes</h3>
      {_table(["User","PID","CPU%","MEM%","Command"], procs_rows, "No processes found")}
    </section>"""


def _section_memory(data):
    m = data["memory"]
    mem_ok = m["usage_pct"] < 85
    swap_ok = m["swap_usage_pct"] < 80

    return f"""
    <section id="memory">
      <h2>🧠 Memory</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">RAM Used</div>
          <div class="metric-value">{m["used_mb"]} / {m["total_mb"]} MB</div>
          {_pct_bar(m["usage_pct"], 75, 90)}
          {_status_badge(mem_ok, "NORMAL", "HIGH")}
        </div>
        <div class="metric-card">
          <div class="metric-label">Available</div>
          <div class="metric-value">{m["available_mb"]} MB</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Cached</div>
          <div class="metric-value">{m["cached_mb"]} MB</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Swap</div>
          <div class="metric-value">{m["swap_used_mb"]} / {m["swap_total_mb"]} MB</div>
          {_pct_bar(m["swap_usage_pct"], 50, 80)}
          {_status_badge(swap_ok, "NORMAL", "HIGH")}
        </div>
      </div>
    </section>"""


def _section_disk(data):
    d = data["disk"]

    part_rows = [
        (
            p["device"], p["mountpoint"], p["size"],
            p["used"], p["available"],
            _pct_bar(p["use_pct"].replace("%",""), 70, 90),
        )
        for p in d["partitions"]
    ]

    large_rows = [
        (f["path"], f"{f['size_mb']} MB")
        for f in d["large_files"]
    ]

    inode_rows = [
        (i["device"], i["mountpoint"], i["total"], i["used"], i["use_pct"])
        for i in d["inodes"]
    ]

    parts_html = _table(
        ["Device", "Mount", "Size", "Used", "Available", "Usage"],
        part_rows, "No partitions found"
    )
    large_html = _table(["Path", "Size"], large_rows, "No large files (>100MB) found")
    inode_html = _table(["Device", "Mount", "Total Inodes", "Used", "Usage%"], inode_rows, "No inode data")

    return f"""
    <section id="disk">
      <h2>💾 Disk</h2>
      <h3>Partitions</h3>{parts_html}
      <h3>Large Files (&gt;100 MB)</h3>{large_html}
      <h3>Inode Usage</h3>{inode_html}
    </section>"""


def _section_network(data):
    n = data["network"]

    iface_rows = [
        (i["name"], i.get("ip","N/A"), f"{i['rx_mb']} MB", f"{i['tx_mb']} MB",
         i["rx_errors"], i["tx_errors"])
        for i in n["interfaces"]
    ]

    port_rows = [
        (p["state"], p["local"], p.get("process","N/A"))
        for p in n["open_ports"]
    ]

    return f"""
    <section id="network">
      <h2>🌐 Network</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Est. Connections</div>
          <div class="metric-value">{n["established_connections"]}</div>
        </div>
      </div>
      <h3>Interfaces</h3>
      {_table(["Interface","IP","RX","TX","RX Errors","TX Errors"], iface_rows, "No interfaces found")}
      <h3>Listening Ports</h3>
      {_table(["State","Local Address","Process"], port_rows, "No open ports")}
    </section>"""


def _section_processes(data):
    p = data["processes"]
    zombie_ok = p["zombies"] == 0

    mem_rows = [
        (proc["user"], proc["pid"], proc["cpu"]+"%", proc["mem"]+"%", proc["command"])
        for proc in p["top_memory"]
    ]

    return f"""
    <section id="processes">
      <h2>⚙️ Processes</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Total Processes</div>
          <div class="metric-value">{p["total"]}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Zombie Processes</div>
          <div class="metric-value">{p["zombies"]}</div>
          {_status_badge(zombie_ok, "NONE", "DETECTED")}
        </div>
      </div>
      <h3>Top Memory Consumers</h3>
      {_table(["User","PID","CPU%","MEM%","Command"], mem_rows, "No process data")}
    </section>"""


def _section_services(data):
    s = data["services"]

    rows = []
    for svc in s["checked"]:
        status_html = (
            '<span class="badge badge-ok">active</span>'
            if svc["active"] else
            f'<span class="badge badge-warn">{svc["status"]}</span>'
        )
        rows.append((svc["name"], status_html))

    failed_rows = [(f,) for f in s["failed_units"]]

    return f"""
    <section id="services">
      <h2>🔧 Services</h2>
      {_table(["Service","Status"], rows, "No services found")}
      <h3>Failed Systemd Units</h3>
      {_table(["Unit"], failed_rows, "✅ No failed units")}
    </section>"""


def _section_security(data):
    sec = data["security"]

    login_rows = [(l,) for l in sec["last_logins"]]
    failed_rows = [(l,) for l in sec["failed_logins_last20"]]
    ww_rows = [(f,) for f in sec["world_writable_sensitive"]]
    logged_rows = [(u,) for u in sec["logged_in_users"]]

    failed_count = len(sec["failed_logins_last20"])
    failed_ok = failed_count < 5

    return f"""
    <section id="security">
      <h2>🔒 Security</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Failed SSH Attempts (last 20 entries)</div>
          <div class="metric-value">{failed_count}</div>
          {_status_badge(failed_ok, "LOW", "HIGH")}
        </div>
        <div class="metric-card">
          <div class="metric-label">SELinux</div>
          <div class="metric-value">{sec["selinux_status"]}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">AppArmor</div>
          <div class="metric-value">{sec["apparmor_status"]}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Pending Security Updates</div>
          <div class="metric-value">{sec["pending_security_updates"]}</div>
        </div>
      </div>
      <h3>Currently Logged-in Users</h3>
      {_table(["Session"], logged_rows, "No active sessions")}
      <h3>Recent Logins</h3>
      {_table(["Entry"], login_rows, "No login history")}
      <h3>Failed SSH Login Attempts (Sample)</h3>
      {_table(["Log Entry"], failed_rows, "✅ No failed attempts in logs")}
      <h3>World-Writable Files in Sensitive Dirs</h3>
      {_table(["File Path"], ww_rows, "✅ None found")}
    </section>"""


def _section_virus(scan_data):
    if not scan_data.get("available"):
        error = scan_data.get("error", "ClamAV not available")
        return f"""
    <section id="virus">
      <h2>🛡️ Virus Scan</h2>
      <div class="alert alert-warn">⚠️ {error}</div>
    </section>"""

    infected = scan_data.get("infected", 0)
    scanned = scan_data.get("scanned", 0)
    ok = infected == 0
    badge_cls = "badge-ok" if ok else "badge-danger"
    badge_label = "CLEAN" if ok else f"{infected} INFECTED"

    inf_rows = [
        (f["path"], f["threat"])
        for f in scan_data.get("infected_files", [])
    ]

    return f"""
    <section id="virus">
      <h2>🛡️ Virus Scan</h2>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="metric-label">Status</div>
          <div class="metric-value"><span class="badge {badge_cls}">{badge_label}</span></div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Files Scanned</div>
          <div class="metric-value">{scanned:,}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Infected</div>
          <div class="metric-value">{infected}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Scan Errors</div>
          <div class="metric-value">{scan_data.get("errors",0)}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Scan Time</div>
          <div class="metric-value">{scan_data.get("scan_time_s","N/A")}s</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Directories Scanned</div>
          <div class="metric-value">{", ".join(scan_data.get("scan_dirs",[]))}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">ClamAV Version</div>
          <div class="metric-value">{scan_data.get("version","N/A")}</div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Started / Finished</div>
          <div class="metric-value">{scan_data.get("started_at","N/A")}<br>{scan_data.get("finished_at","N/A")}</div>
        </div>
      </div>
      <h3>Infected Files</h3>
      {_table(["File Path","Threat"], inf_rows, "✅ No infected files found")}
    </section>"""


# ─────────────────────────── SUMMARY BAR ────────────────────────────────────

def _overall_summary(health_data, scan_data):
    checks = []

    # CPU
    try:
        cpu_ok = float(health_data["cpu"]["usage_pct"]) < 80
    except Exception:
        cpu_ok = True
    checks.append(("CPU", cpu_ok))

    # Memory
    mem_ok = health_data["memory"]["usage_pct"] < 85
    checks.append(("Memory", mem_ok))

    # Disk
    disk_ok = all(
        int(p["use_pct"].replace("%","")) < 90
        for p in health_data["disk"]["partitions"]
        if p["use_pct"].replace("%","").isdigit()
    )
    checks.append(("Disk", disk_ok))

    # Virus
    if scan_data.get("available"):
        virus_ok = scan_data.get("infected", 0) == 0
        checks.append(("Virus Scan", virus_ok))
    else:
        checks.append(("Virus Scan", None))

    # Zombies
    zombie_ok = health_data["processes"]["zombies"] == 0
    checks.append(("Processes", zombie_ok))

    # Services
    svc_ok = len(health_data["services"]["failed_units"]) == 0
    checks.append(("Services", svc_ok))

    items_html = ""
    for name, status in checks:
        if status is None:
            cls = "summary-unknown"
            icon = "⚪"
        elif status:
            cls = "summary-ok"
            icon = "✅"
        else:
            cls = "summary-warn"
            icon = "⚠️"
        items_html += f'<div class="summary-item {cls}">{icon} {name}</div>'

    all_ok = all(s for _, s in checks if s is not None)
    overall_class = "overall-ok" if all_ok else "overall-warn"
    overall_text = "ALL SYSTEMS HEALTHY" if all_ok else "ATTENTION REQUIRED"

    return f"""
    <div class="summary-banner {overall_class}">
      <div class="overall-status">{overall_text}</div>
      <div class="summary-items">{items_html}</div>
    </div>"""


# ─────────────────────────── HTML TEMPLATE ──────────────────────────────────

def _html_template(body, summary, ts, hostname):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Health Check — {hostname} — {ts}</title>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --accent: #6366f1;
      --accent2: #818cf8;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --ok: #4ade80;
      --warn: #facc15;
      --danger: #f87171;
      --border: rgba(255,255,255,0.07);
      --radius: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, sans-serif;
      font-size: 14px;
      line-height: 1.6;
    }}
    header {{
      background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #1e1b4b 100%);
      padding: 36px 40px;
      border-bottom: 1px solid var(--border);
    }}
    header h1 {{
      font-size: 2rem;
      font-weight: 700;
      background: linear-gradient(90deg, #a5b4fc, #e879f9);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }}
    header p {{ color: var(--text-muted); font-size: 0.9rem; }}
    nav {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0 40px;
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}
    nav a {{
      color: var(--text-muted);
      text-decoration: none;
      padding: 12px 16px;
      font-size: 0.85rem;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }}
    nav a:hover {{ color: var(--accent2); border-bottom-color: var(--accent2); }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 40px; }}
    .summary-banner {{
      border-radius: var(--radius);
      padding: 24px 28px;
      margin-bottom: 32px;
      border: 1px solid var(--border);
    }}
    .overall-ok {{ background: linear-gradient(135deg, rgba(74,222,128,0.1), rgba(74,222,128,0.05)); border-color: rgba(74,222,128,0.3); }}
    .overall-warn {{ background: linear-gradient(135deg, rgba(248,113,113,0.1), rgba(248,113,113,0.05)); border-color: rgba(248,113,113,0.3); }}
    .overall-status {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 16px; }}
    .overall-ok .overall-status {{ color: var(--ok); }}
    .overall-warn .overall-status {{ color: var(--danger); }}
    .summary-items {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .summary-item {{
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
    }}
    .summary-ok {{ background: rgba(74,222,128,0.15); color: var(--ok); }}
    .summary-warn {{ background: rgba(248,113,113,0.15); color: var(--danger); }}
    .summary-unknown {{ background: rgba(148,163,184,0.15); color: var(--text-muted); }}
    section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 28px;
      margin-bottom: 24px;
    }}
    section h2 {{
      font-size: 1.2rem;
      font-weight: 700;
      margin-bottom: 20px;
      color: var(--accent2);
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
    }}
    section h3 {{
      font-size: 0.95rem;
      font-weight: 600;
      margin: 20px 0 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }}
    .metric-card {{
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .metric-label {{
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 1.4rem;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    th {{
      background: var(--surface2);
      color: var(--text-muted);
      text-align: left;
      padding: 10px 14px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 0.75rem;
      border-bottom: 1px solid var(--border);
    }}
    td {{
      padding: 9px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--text);
      word-break: break-all;
      max-width: 400px;
    }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .info-table td.key {{
      color: var(--text-muted);
      font-weight: 600;
      width: 200px;
      word-break: normal;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 20px;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 6px;
    }}
    .badge-ok {{ background: rgba(74,222,128,0.15); color: var(--ok); }}
    .badge-warn {{ background: rgba(250,204,21,0.15); color: var(--warn); }}
    .badge-danger {{ background: rgba(248,113,113,0.15); color: var(--danger); }}
    .bar-wrap {{
      background: rgba(255,255,255,0.06);
      border-radius: 4px;
      height: 6px;
      position: relative;
      margin: 6px 0 2px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s;
    }}
    .bar-label {{
      font-size: 0.7rem;
      color: var(--text-muted);
    }}
    .alert-warn {{
      background: rgba(250,204,21,0.1);
      border: 1px solid rgba(250,204,21,0.3);
      color: var(--warn);
      border-radius: 8px;
      padding: 14px 18px;
    }}
    .empty {{ color: var(--text-muted); font-style: italic; padding: 12px 0; }}
    .na {{ color: var(--text-muted); }}
    footer {{
      text-align: center;
      padding: 32px;
      color: var(--text-muted);
      font-size: 0.8rem;
      border-top: 1px solid var(--border);
    }}
    @media(max-width:768px) {{
      .container {{ padding: 16px; }}
      header {{ padding: 20px 16px; }}
      nav {{ padding: 0 16px; }}
      .metric-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
<header>
  <h1>🔍 Server Health Check</h1>
  <p>Host: <strong>{hostname}</strong> &nbsp;|&nbsp; Generated: <strong>{ts}</strong></p>
</header>
<nav>
  <a href="#os">System</a>
  <a href="#cpu">CPU</a>
  <a href="#memory">Memory</a>
  <a href="#disk">Disk</a>
  <a href="#network">Network</a>
  <a href="#processes">Processes</a>
  <a href="#services">Services</a>
  <a href="#security">Security</a>
  <a href="#virus">Virus Scan</a>
</nav>
<div class="container">
  {summary}
  {body}
</div>
<footer>
  Generated by <strong>healthcheck.py</strong> &nbsp;|&nbsp; {ts}
</footer>
</body>
</html>"""


# ─────────────────────────── MAIN EXPORT ────────────────────────────────────

def generate_report(health_data, scan_data, output_dir=OUTPUT_DIR):
    """
    Generate HTML + JSON reports and save to output_dir.

    Returns dict with paths of generated files.
    """
    os.makedirs(output_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    hostname = health_data["os"]["hostname"]

    # Build HTML sections
    body_parts = [
        _section_os(health_data),
        _section_cpu(health_data),
        _section_memory(health_data),
        _section_disk(health_data),
        _section_network(health_data),
        _section_processes(health_data),
        _section_services(health_data),
        _section_security(health_data),
        _section_virus(scan_data),
    ]
    body = "\n".join(body_parts)
    summary = _overall_summary(health_data, scan_data)

    html = _html_template(body, summary, ts, hostname)

    # File paths
    html_path = os.path.join(output_dir, f"healthcheck_{ts}.html")
    json_path = os.path.join(output_dir, f"healthcheck_{ts}.json")
    latest_path = os.path.join(output_dir, "latest.html")

    # Write HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Write JSON
    full_data = {
        "meta": {"generated_at": ts, "hostname": hostname},
        "health": health_data,
        "virus_scan": scan_data,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, indent=2, default=str)

    # Update latest symlink / copy
    try:
        if os.path.islink(latest_path):
            os.remove(latest_path)
        os.symlink(html_path, latest_path)
    except Exception:
        # On systems where symlinks fail, just copy
        import shutil
        shutil.copy2(html_path, latest_path)

    return {
        "html": html_path,
        "json": json_path,
        "latest": latest_path,
    }
