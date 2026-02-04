#!/usr/bin/env python3
"""
Network Radar - Connection Monitoring Service
A self-hosted monitoring solution similar to radar.chabokan.net
"""

import asyncio
import json
import time
import socket
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from pathlib import Path
import sqlite3
import os


def utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)

import aiohttp
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yaml

app = Flask(__name__)
CORS(app)

from flask import send_from_directory

@app.route('/favicon.ico')
def favicon():
    # Prefer static/favicon.ico if present, otherwise serve root-level favicon.ico
    static_favicon = os.path.join(app.root_path, 'static', 'favicon.ico')
    if os.path.exists(static_favicon):
        return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/x-icon')
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/x-icon')

# Global storage for monitoring results
monitoring_results: Dict[str, dict] = {}
results_lock = threading.Lock()

@dataclass
class Target:
    name: str
    host: str
    type: str  # ping, http, tcp, dns
    port: Optional[int] = None
    category: str = "general"
    description: str = ""
    check_interval: int = 30  # seconds

@dataclass
class CheckResult:
    target_name: str
    status: str  # online, offline, degraded
    latency_ms: float
    timestamp: str
    error: Optional[str] = None
    details: Optional[dict] = None

# Database and app config globals
DB_CONN = None
DB_LOCK = threading.Lock()
APP_CONFIG = {}

def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Config file not found: {config_path}, using defaults")
        return {
            "check_interval": 30,
            "history_size": 100,
            "web_port": 5000,
            "db_path": "data.db",
            "targets": []
        }
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def init_db(db_path: str):
    """Initialize SQLite database and create required tables"""
    global DB_CONN
    DB_CONN = sqlite3.connect(db_path, check_same_thread=False)
    DB_CONN.row_factory = sqlite3.Row
    # Always ensure tables exist
    with DB_CONN:
        DB_CONN.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            target_name TEXT,
            host TEXT,
            type TEXT,
            status TEXT,
            latency_ms REAL,
            timestamp TEXT,
            error TEXT,
            details TEXT
        );
        """)
        DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_checks_timestamp ON checks(timestamp);")
        DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_checks_agent ON checks(agent_id);")
    print(f"[INFO] Database initialized: {db_path}")

# Initialize database at module load (for gunicorn)
_config = load_config()
APP_CONFIG = _config
init_db(_config.get('db_path', 'data.db'))

def init_db(db_path: str):
    """Initialize SQLite database and create required tables"""
    global DB_CONN
    DB_CONN = sqlite3.connect(db_path, check_same_thread=False)
    DB_CONN.row_factory = sqlite3.Row
    # Always ensure tables exist
    with DB_CONN:
        DB_CONN.execute("""
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT,
            target_name TEXT,
            host TEXT,
            type TEXT,
            status TEXT,
            latency_ms REAL,
            timestamp TEXT,
            error TEXT,
            details TEXT
        );
        """)
        DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_checks_timestamp ON checks(timestamp);")
        DB_CONN.execute("CREATE INDEX IF NOT EXISTS idx_checks_agent ON checks(agent_id);")
    print(f"[INFO] Database initialized: {db_path}")


def insert_check(agent_id: str, target: dict, result: 'CheckResult'):
    """Insert a single check result into the DB"""
    details = json.dumps(result.details) if result.details else None
    host = target.get('host') if isinstance(target, dict) else None
    typ = target.get('type') if isinstance(target, dict) else None
    with DB_LOCK:
        with DB_CONN:
            DB_CONN.execute(
                """INSERT INTO checks (agent_id, target_name, host, type, status, latency_ms, timestamp, error, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (agent_id, result.target_name, host, typ, result.status, result.latency_ms, result.timestamp, result.error, details)
            )


def get_latest_statuses():
    """Return the latest check per (agent_id, target_name)"""
    with DB_LOCK:
        cur = DB_CONN.cursor()
        cur.execute("""
            SELECT c.agent_id, c.target_name, c.host, c.type, c.status, c.latency_ms, c.timestamp, c.error, c.details
            FROM checks c
            INNER JOIN (
                SELECT MAX(id) as max_id FROM checks GROUP BY agent_id, target_name
            ) m ON c.id = m.max_id
        """)
        rows = cur.fetchall()
    return rows


def get_history(target_name: str, hours: int = 24):
    """Return history rows for a given target (across agents) in the last N hours"""
    cutoff = utcnow() - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()
    with DB_LOCK:
        cur = DB_CONN.cursor()
        cur.execute("""
            SELECT agent_id, target_name, host, type, status, latency_ms, timestamp, error, details
            FROM checks
            WHERE target_name = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (target_name, cutoff_iso))
        rows = cur.fetchall()
    # Convert rows to dicts
    result = []
    for r in rows:
        # Ensure details is JSON-deserializable and decode bytes if needed
        details_raw = r['details']
        details_parsed = None
        if details_raw:
            try:
                if isinstance(details_raw, (bytes, bytearray)):
                    details_raw = details_raw.decode('utf-8', errors='ignore')
                details_parsed = json.loads(details_raw)
            except Exception:
                # Fallback: store as string
                try:
                    details_parsed = str(details_raw)
                except Exception:
                    details_parsed = None

        result.append({
            'agent_id': r['agent_id'],
            'target_name': r['target_name'],
            'host': r['host'],
            'type': r['type'],
            'status': r['status'],
            'latency_ms': r['latency_ms'],
            'timestamp': r['timestamp'],
            'error': r['error'],
            'details': details_parsed
        })
    return result


def get_recent_history(agent_id: str, target_name: str, limit: int = 60):
    """Return recent history for a specific agent/target pair"""
    with DB_LOCK:
        cur = DB_CONN.cursor()
        cur.execute("""
            SELECT status, latency_ms, timestamp
            FROM checks
            WHERE agent_id = ? AND target_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (agent_id, target_name, limit))
        rows = cur.fetchall()
    # Return in chronological order (oldest first)
    return [{'status': r['status'], 'latency_ms': r['latency_ms'], 'timestamp': r['timestamp']} for r in reversed(rows)]


def cleanup_old_records_loop(retention_hours: int):
    """Background loop to delete records older than retention_hours"""
    seconds = retention_hours * 3600
    while True:
        cutoff = utcnow() - timedelta(seconds=seconds)
        cutoff_iso = cutoff.isoformat()
        with DB_LOCK:
            with DB_CONN:
                DB_CONN.execute("DELETE FROM checks WHERE timestamp < ?", (cutoff_iso,))
        time.sleep(3600)


def ping_host(host: str, count: int = 3) -> tuple[bool, float, Optional[str]]:
    """Ping a host and return (success, avg_latency_ms, error)"""
    import platform
    try:
        # Windows uses -n for count and -w for timeout (in ms), Linux uses -c and -W
        if platform.system().lower() == 'windows':
            result = subprocess.run(
                ['ping', '-n', str(count), '-w', '2000', host],
                capture_output=True,
                text=True,
                timeout=15
            )
        else:
            result = subprocess.run(
                ['ping', '-c', str(count), '-W', '2', host],
                capture_output=True,
                text=True,
                timeout=10
            )
        
        if result.returncode == 0:
            # Parse average latency from ping output
            output = result.stdout
            # Try Linux format first: rtt min/avg/max/mdev = 1.234/5.678/9.012/1.234 ms
            for line in output.split('\n'):
                if 'avg' in line or 'rtt' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        times = parts[1].strip().split('/')
                        if len(times) >= 2:
                            return True, float(times[1]), None
            # Try Windows format: Average = XXms or Average = XXms (Persian: میانگین)
            import re
            # Windows English: Average = 25ms
            match = re.search(r'Average\s*=\s*(\d+)\s*ms', output, re.IGNORECASE)
            if match:
                return True, float(match.group(1)), None
            # Windows: look for time=XXms patterns and average them
            times = re.findall(r'time[=<](\d+)\s*ms', output, re.IGNORECASE)
            if times:
                avg = sum(int(t) for t in times) / len(times)
                return True, avg, None
            return True, 0.0, None
        else:
            return False, 0.0, "Host unreachable"
    except subprocess.TimeoutExpired:
        return False, 0.0, "Timeout"
    except Exception as e:
        return False, 0.0, str(e)

async def check_http(url: str, timeout: int = 10) -> tuple[bool, float, Optional[str], dict]:
    """Check HTTP endpoint and return (success, latency_ms, error, details)"""
    start_time = time.time()
    details = {}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), 
                                   ssl=False, allow_redirects=True) as response:
                latency = (time.time() - start_time) * 1000
                details['status_code'] = response.status
                details['content_type'] = response.headers.get('Content-Type', 'unknown')
                
                if 200 <= response.status < 400:
                    return True, latency, None, details
                else:
                    return False, latency, f"HTTP {response.status}", details
    except asyncio.TimeoutError:
        return False, 0.0, "Timeout", details
    except aiohttp.ClientError as e:
        return False, 0.0, str(e), details
    except Exception as e:
        return False, 0.0, str(e), details

def check_tcp(host: str, port: int, timeout: int = 5) -> tuple[bool, float, Optional[str]]:
    """Check TCP port connectivity"""
    start_time = time.time()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        latency = (time.time() - start_time) * 1000
        sock.close()
        
        if result == 0:
            return True, latency, None
        else:
            return False, latency, f"Connection refused (error: {result})"
    except socket.timeout:
        return False, 0.0, "Timeout"
    except socket.gaierror as e:
        return False, 0.0, f"DNS resolution failed: {e}"
    except Exception as e:
        return False, 0.0, str(e)

def check_dns(host: str, dns_server: str = "8.8.8.8") -> tuple[bool, float, Optional[str]]:
    """Check DNS resolution"""
    start_time = time.time()
    
    try:
        result = subprocess.run(
            ['dig', '+short', '+time=2', '+tries=1', f'@{dns_server}', host],
            capture_output=True,
            text=True,
            timeout=5
        )
        latency = (time.time() - start_time) * 1000
        
        if result.returncode == 0 and result.stdout.strip():
            return True, latency, None
        else:
            return False, latency, "DNS resolution failed"
    except subprocess.TimeoutExpired:
        return False, 0.0, "Timeout"
    except FileNotFoundError:
        # dig not installed, fallback to socket
        try:
            socket.gethostbyname(host)
            latency = (time.time() - start_time) * 1000
            return True, latency, None
        except socket.gaierror as e:
            return False, 0.0, str(e)
    except Exception as e:
        return False, 0.0, str(e)

async def check_target(target: dict) -> CheckResult:
    """Check a single target based on its type"""
    target_type = target.get('type', 'ping')
    host = target['host']
    name = target['name']
    
    success = False
    latency = 0.0
    error = None
    details = None
    
    if target_type == 'ping':
        success, latency, error = ping_host(host)
    elif target_type == 'http':
        success, latency, error, details = await check_http(host)
    elif target_type == 'tcp':
        port = target.get('port', 80)
        success, latency, error = check_tcp(host, port)
    elif target_type == 'dns':
        dns_server = target.get('dns_server', '8.8.8.8')
        success, latency, error = check_dns(host, dns_server)
    
    # Determine status
    if success:
        if latency > 500:
            status = 'degraded'
        else:
            status = 'online'
    else:
        status = 'offline'
    
    return CheckResult(
        target_name=name,
        status=status,
        latency_ms=round(latency, 2),
        timestamp=datetime.now().isoformat(),
        error=error,
        details=details
    )

async def run_checks(config: dict):
    """Run all monitoring checks"""
    targets = config.get('targets', [])
    tasks = [check_target(t) for t in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    agent_id = config.get('agent_id', 'local')

    with results_lock:
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                result = CheckResult(
                    target_name=targets[i]['name'],
                    status='offline',
                    latency_ms=0.0,
                    timestamp=utcnow().isoformat(),
                    error=str(result)
                )
            else:
                # Ensure UTC timestamp for consistency
                result.timestamp = utcnow().isoformat()

            # Insert into DB for persistence
            try:
                insert_check(agent_id, targets[i], result)
            except Exception as e:
                print(f"DB insert error: {e}")

            target_name = result.target_name
            if target_name not in monitoring_results:
                monitoring_results[target_name] = {
                    'current': None,
                    'history': [],
                    'config': targets[i]
                }

            monitoring_results[target_name]['current'] = asdict(result)

            # Keep history
            history = monitoring_results[target_name]['history']
            history.append(asdict(result))
            if len(history) > config.get('history_size', 100):
                history.pop(0)

def monitoring_loop(config: dict):
    """Background monitoring loop"""
    interval = config.get('check_interval', 30)
    
    while True:
        try:
            asyncio.run(run_checks(config))
        except Exception as e:
            print(f"Monitoring error: {e}")
        time.sleep(interval)

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    # Build a targets dict from the latest DB rows
    rows = get_latest_statuses()
    targets = {}

    # Get hours parameter from query string (default to 1 hour)
    try:
        hours = int(request.args.get('hours', 1))
        hours = max(1, min(hours, 24))  # Clamp between 1 and 24
    except:
        hours = 1
    
    # Calculate appropriate limit based on time range
    # Assuming checks every minute: 60 per hour
    limit = hours * 60

    # Build map of target_name -> icon from loaded APP_CONFIG
    target_icon_map = {}
    for t in APP_CONFIG.get('targets', []):
        if isinstance(t, dict) and t.get('name') and t.get('icon'):
            target_icon_map[t.get('name')] = t.get('icon')

    for r in rows:
        key = f"{r['agent_id']} :: {r['target_name']}"
        # Get recent history for this target/agent based on time range
        history = get_recent_history(r['agent_id'], r['target_name'], limit=limit)
        targets[key] = {
            'current': {
                'target_name': r['target_name'],
                'status': r['status'],
                'latency_ms': r['latency_ms'],
                'timestamp': r['timestamp'],
                'error': r['error'],
                'details': json.loads(r['details']) if r['details'] else None
            },
            'config': {
                'host': r['host'],
                'type': r['type'],
                'icon': target_icon_map.get(r['target_name'])
            },
            'history': history
        }

    return jsonify({
        'timestamp': utcnow().isoformat(),
        'targets': targets
    })

@app.route('/api/ingest', methods=['POST'])
def api_ingest():
    """Endpoint for agents to POST a batch of check results"""
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != APP_CONFIG.get('api_key'):
        return jsonify({'error': 'Unauthorized'}), 401

    payload = request.get_json()
    if not payload or 'checks' not in payload:
        return jsonify({'error': 'Invalid payload'}), 400

    agent_id = payload.get('agent_id', 'unknown')
    checks = payload.get('checks', [])
    inserted = 0
    for c in checks:
        try:
            cr = CheckResult(
                target_name=c.get('target_name'),
                status=c.get('status'),
                latency_ms=c.get('latency_ms', 0.0),
                timestamp=c.get('timestamp', utcnow().isoformat()),
                error=c.get('error'),
                details=c.get('details')
            )
            insert_check(agent_id, {'host': c.get('host'), 'type': c.get('type')}, cr)
            inserted += 1
        except Exception as e:
            print(f"Error inserting check from ingest: {e}")

    return jsonify({'status': 'ok', 'received': inserted})


@app.route('/api/target/<name>')
def api_target(name: str):
    # Return history for this target across agents (last 24 hours by default)
    try:
        hours = int(request.args.get('hours', 24))
        history = get_history(name, hours)
        if not history:
            return jsonify({'error': 'Target not found or no recent data'}), 404
        return jsonify({'target': name, 'history': history})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error in api_target: {e}\n{tb}")
        return jsonify({'error': 'internal', 'message': str(e), 'trace': tb}), 500


@app.route('/api/summary')
def api_summary():
    # Compute summary from latest DB rows
    rows = get_latest_statuses()
    total = len(rows)
    online = sum(1 for r in rows if r['status'] == 'online')
    degraded = sum(1 for r in rows if r['status'] == 'degraded')
    offline = sum(1 for r in rows if r['status'] == 'offline')

    return jsonify({
        'total': total,
        'online': online,
        'degraded': degraded,
        'offline': offline,
        'timestamp': utcnow().isoformat()
    })


# DEBUG: Endpoint to inspect DB rows for a given target (only for local debugging)
@app.route('/debug/target_rows/<name>')
def debug_target_rows(name: str):
    try:
        cutoff = (utcnow() - timedelta(hours=24)).isoformat()
        with DB_LOCK:
            cur = DB_CONN.cursor()
            cur.execute("""
                SELECT agent_id, target_name, host, type, status, latency_ms, timestamp, error, details
                FROM checks
                WHERE target_name = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT 20
            """, (name, cutoff))
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return jsonify({'count': len(rows), 'rows': rows})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Debug endpoint error: {e}\n{tb}")
        return jsonify({'error': str(e), 'trace': tb}), 500


@app.route('/debug/routes')
def debug_routes():
    try:
        rules = [r.rule for r in app.url_map.iter_rules()]
        return jsonify({'routes': rules})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Debug routes error: {e}\n{tb}")
        return jsonify({'error': str(e), 'trace': tb}), 500

def main():
    global APP_CONFIG
    config = APP_CONFIG  # Already loaded at module level

    # Configure rate limiter
    limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])
    limiter.init_app(app)

    # Start monitoring and cleanup threads only in the real process (avoid Werkzeug reloader duplication)
    run_background = (not app.debug) or (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
    if run_background:
        monitor_thread = threading.Thread(target=monitoring_loop, args=(config,), daemon=True)
        monitor_thread.start()

        # Start cleanup thread for old records
        cleanup_thread = threading.Thread(target=cleanup_old_records_loop, args=(config.get('retention_hours', 24),), daemon=True)
        cleanup_thread.start()

        # Run initial check once
        try:
            asyncio.run(run_checks(config))
        except Exception as e:
            print(f"Initial run_checks error: {e}")
    else:
        print("Skipping background monitoring in reloader parent process")

    # Start web server (gunicorn recommended in Dockerfile)
    port = config.get('web_port', 5000)
    print(f"🚀 Network Radar starting on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == '__main__':
    main()
