#!/usr/bin/env python3
"""Fail2ban HTTP Bridge — xCut SA Firewall Panel"""
import subprocess, json, os, configparser, re, time, shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PORT       = 7655
TOKEN      = os.environ.get("FAIL2BAN_TOKEN", "xcut-f2b-bridge-2026")
JAIL_LOCAL = "/etc/fail2ban/jail.local"
F2B_LOG    = "/var/log/fail2ban.log"

# ── fail2ban-client helpers ───────────────────────────────────────────────────

def f2b(*args):
    r = subprocess.run(["fail2ban-client"] + list(args),
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip()

def get_active_jails():
    out = f2b("status")
    for line in out.split("\n"):
        if "Jail list" in line:
            raw = line.split(":", 1)[-1].strip()
            return [j.strip() for j in raw.split(",") if j.strip()]
    return []

def get_jail_status(jail):
    out = f2b("status", jail)
    r = {"name": jail, "currently_banned": 0, "total_banned": 0, "total_failed": 0, "banned_ips": []}
    for line in out.split("\n"):
        line = line.strip()
        if "Currently banned" in line:
            try: r["currently_banned"] = int(line.split(":")[-1].strip())
            except: pass
        elif "Total banned" in line:
            try: r["total_banned"] = int(line.split(":")[-1].strip())
            except: pass
        elif "Total failed" in line:
            try: r["total_failed"] = int(line.split(":")[-1].strip())
            except: pass
        elif "Banned IP list" in line:
            ips = line.split(":", 1)[-1].strip()
            r["banned_ips"] = [ip for ip in ips.split() if ip]
    return r

# ── jail.local helpers ────────────────────────────────────────────────────────

def parse_jail_local():
    cfg = configparser.RawConfigParser(allow_no_value=True, strict=False)
    cfg.read(JAIL_LOCAL)
    result = []
    for section in cfg.sections():
        j = {"name": section}
        for key in ("enabled", "filter", "logpath", "maxretry", "bantime",
                    "findtime", "ignoreip", "port", "action", "destemail", "backend"):
            val = cfg.get(section, key, fallback=None)
            if val is not None:
                j[key] = val
        result.append(j)
    return result

def write_jail_local(jails):
    defaults = [j for j in jails if j.get("name", "").upper() == "DEFAULT"]
    others   = [j for j in jails if j.get("name", "").upper() != "DEFAULT"]
    lines = []
    for jail in defaults + others:
        lines.append(f"[{jail['name']}]")
        for key, val in jail.items():
            if key == "name" or val is None or str(val).strip() == "":
                continue
            lines.append(f"{key} = {val}")
        lines.append("")
    with open(JAIL_LOCAL, "w") as f:
        f.write("\n".join(lines))
    subprocess.run(["fail2ban-client", "reload"], capture_output=True, timeout=20)

# ── log parser ────────────────────────────────────────────────────────────────

LOG_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+'
    r'fail2ban\.(\w+)\s+\[\d+\]:\s+(\w+)\s+(.*)'
)
JAIL_MSG_RE = re.compile(r'^\[([^\]]+)\]\s+(.*)')

LEVEL_PRIORITY = {"ERROR": 0, "WARNING": 1, "NOTICE": 2, "INFO": 3, "DEBUG": 4}

def parse_log(lines_count=500, min_level="NOTICE"):
    min_p = LEVEL_PRIORITY.get(min_level, 2)
    events = []
    try:
        with open(F2B_LOG, "r") as f:
            all_lines = f.readlines()
        recent = all_lines[-lines_count:] if len(all_lines) > lines_count else all_lines
        for line in reversed(recent):
            m = LOG_RE.match(line.strip())
            if not m:
                continue
            ts, module, level, message = m.groups()
            if LEVEL_PRIORITY.get(level, 99) > min_p:
                continue
            jail_m = JAIL_MSG_RE.match(message)
            jail   = jail_m.group(1) if jail_m else None
            action = jail_m.group(2) if jail_m else message
            action_type = "info"
            if level in ("ERROR", "WARNING"):
                action_type = "error" if level == "ERROR" else "warning"
            elif "Ban " in action:
                action_type = "ban"
            elif "Unban " in action:
                action_type = "unban"
            elif "Found " in action:
                action_type = "found"
            elif "started" in action.lower() or "stopped" in action.lower():
                action_type = "system"
            ip = None
            ip_m = re.search(r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', action)
            if ip_m:
                ip = ip_m.group(1)
            events.append({
                "timestamp":  ts,
                "module":     module,
                "level":      level,
                "jail":       jail,
                "action":     action,
                "actionType": action_type,
                "ip":         ip,
            })
    except Exception as e:
        return [{"timestamp": "", "level": "ERROR", "action": str(e), "actionType": "error",
                 "module": "bridge", "jail": None, "ip": None}]
    return events

# ── system stats ──────────────────────────────────────────────────────────────

_prev_cpu  = None
_prev_net  = None

def _read_cpu_times():
    with open("/proc/stat") as f:
        parts = f.readline().split()
    vals = [int(x) for x in parts[1:]]
    idle  = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
    total = sum(vals)
    return total, idle

def get_cpu_percent():
    global _prev_cpu
    cur = _read_cpu_times()
    if _prev_cpu is None:
        _prev_cpu = cur
        time.sleep(0.25)
        cur = _read_cpu_times()
    dt_total = cur[0] - _prev_cpu[0]
    dt_idle  = cur[1] - _prev_cpu[1]
    _prev_cpu = cur
    if dt_total == 0:
        return 0.0
    return round(100.0 * (1 - dt_idle / dt_total), 1)

def get_memory():
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            p = line.split()
            if len(p) >= 2:
                mem[p[0].rstrip(":")] = int(p[1])
    total     = mem.get("MemTotal",     0)
    available = mem.get("MemAvailable", 0)
    used      = total - available
    return {
        "total_mb":     total // 1024,
        "used_mb":      used  // 1024,
        "available_mb": available // 1024,
        "percent":      round(100.0 * used / total, 1) if total else 0,
    }

def get_disk():
    usage = shutil.disk_usage("/")
    return {
        "total_gb": round(usage.total / 1073741824, 1),
        "used_gb":  round(usage.used  / 1073741824, 1),
        "free_gb":  round(usage.free  / 1073741824, 1),
        "percent":  round(100.0 * usage.used / usage.total, 1),
    }

def get_uptime():
    with open("/proc/uptime") as f:
        secs = float(f.read().split()[0])
    d = int(secs // 86400)
    h = int((secs % 86400) // 3600)
    m = int((secs % 3600) // 60)
    return {"seconds": int(secs), "days": d, "hours": h, "minutes": m}

def get_load():
    with open("/proc/loadavg") as f:
        p = f.read().split()
    return {"1m": float(p[0]), "5m": float(p[1]), "15m": float(p[2])}

def get_network():
    global _prev_net
    ifaces = {}
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            p = line.split()
            if len(p) < 10:
                continue
            iface = p[0].rstrip(":")
            if iface == "lo":
                continue
            ifaces[iface] = {"rx": int(p[1]), "tx": int(p[9])}
    now    = time.time()
    result = []
    for iface, cur in ifaces.items():
        if _prev_net:
            dt   = now - _prev_net["time"]
            prev = _prev_net["ifaces"].get(iface, cur)
            rx_r = max(0, (cur["rx"] - prev["rx"]) / dt) if dt > 0 else 0
            tx_r = max(0, (cur["tx"] - prev["tx"]) / dt) if dt > 0 else 0
        else:
            rx_r = tx_r = 0
        result.append({
            "interface": iface,
            "rx_bps":    int(rx_r),
            "tx_bps":    int(tx_r),
            "rx_total":  cur["rx"],
            "tx_total":  cur["tx"],
        })
    _prev_net = {"time": now, "ifaces": ifaces}
    return result

def get_top_processes(n=8):
    try:
        out = subprocess.run(
            ["ps", "aux", "--sort=-%cpu"],
            capture_output=True, text=True, timeout=5
        ).stdout.splitlines()
        procs = []
        for line in out[1:n+1]:
            p = line.split(None, 10)
            if len(p) < 11:
                continue
            procs.append({
                "user":    p[0],
                "pid":     p[1],
                "cpu":     float(p[2]),
                "mem":     float(p[3]),
                "command": p[10][:60],
            })
        return procs
    except Exception:
        return []

def get_system_stats():
    return {
        "cpu_percent": get_cpu_percent(),
        "memory":      get_memory(),
        "disk":        get_disk(),
        "uptime":      get_uptime(),
        "load":        get_load(),
        "network":     get_network(),
        "processes":   get_top_processes(),
    }

# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def check_auth(self):
        return self.headers.get("X-F2B-Token") == TOKEN

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def qs(self):
        return parse_qs(urlparse(self.path).query)

    def path_base(self):
        return urlparse(self.path).path

    def do_GET(self):
        if not self.check_auth():
            self.send_json({"error": "Unauthorized"}, 401); return

        base = self.path_base()
        qs   = self.qs()

        if base == "/status":
            try:
                jails  = get_active_jails()
                result = [get_jail_status(j) for j in jails]
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif base == "/status-full":
            try:
                active     = set(get_active_jails())
                cfg        = parse_jail_local()
                status_map = {j: get_jail_status(j) for j in active}
                result = []
                default_item = None
                for jail_cfg in cfg:
                    name = jail_cfg["name"]
                    if name.upper() == "DEFAULT":
                        default_item = {
                            "name": "DEFAULT", "isDefault": True, "active": True,
                            "currently_banned": 0, "total_banned": 0,
                            "total_failed": 0, "banned_ips": [], "config": jail_cfg
                        }
                    else:
                        st = status_map.get(name, {
                            "name": name, "currently_banned": 0,
                            "total_banned": 0, "total_failed": 0, "banned_ips": []
                        })
                        result.append({**st, "isDefault": False, "active": name in active, "config": jail_cfg})
                if default_item:
                    result.insert(0, default_item)
                self.send_json(result)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif base == "/config":
            try:
                self.send_json(parse_jail_local())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif base == "/logs":
            try:
                lines_count = int(qs.get("lines", ["500"])[0])
                min_level   = qs.get("level", ["NOTICE"])[0].upper()
                self.send_json(parse_log(lines_count, min_level))
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif base == "/system-stats":
            try:
                self.send_json(get_system_stats())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif base == "/ping":
            self.send_json({"ok": True})

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_PUT(self):
        if not self.check_auth():
            self.send_json({"error": "Unauthorized"}, 401); return

        if self.path_base() == "/config":
            try:
                body  = self.read_body()
                jails = body.get("jails", [])
                if not jails:
                    self.send_json({"error": "jails required"}, 400); return
                write_jail_local(jails)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.check_auth():
            self.send_json({"error": "Unauthorized"}, 401); return
        body = self.read_body()

        if self.path_base() == "/unban":
            jail = body.get("jail", "")
            ip   = body.get("ip", "")
            if not jail or not ip:
                self.send_json({"error": "jail and ip required"}, 400); return
            try:
                f2b("set", jail, "unbanip", ip)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif self.path_base() == "/ban":
            jail = body.get("jail", "")
            ip   = body.get("ip", "")
            if not jail or not ip:
                self.send_json({"error": "jail and ip required"}, 400); return
            try:
                f2b("set", jail, "banip", ip)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif self.path_base() == "/reload":
            try:
                subprocess.run(["fail2ban-client", "reload"], capture_output=True, timeout=20)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        else:
            self.send_json({"error": "Not found"}, 404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Fail2ban bridge :{PORT}", flush=True)
    server.serve_forever()
