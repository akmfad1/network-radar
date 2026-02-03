#!/usr/bin/env python3
"""Agent for Network Radar - runs checks and sends results to Display server"""
import asyncio
import json
import os
import time
import socket
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import yaml


def utcnow():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


CONFIG_PATH = os.environ.get('AGENT_CONFIG', 'agent_config.yaml')
DISPLAY_URL = os.environ.get('DISPLAY_URL', 'http://localhost:5000')
API_KEY = os.environ.get('API_KEY', '')
AGENT_ID = os.environ.get('AGENT_ID') or socket.gethostname()

@dataclass
class Target:
    name: str
    host: str
    type: str
    port: int = None

async def check_http(session, url: str, timeout: int = 10):
    start = time.time()
    details = {}
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), ssl=True) as resp:
            latency = (time.time() - start) * 1000
            details['status_code'] = resp.status
            details['content_type'] = resp.headers.get('Content-Type')
            if 200 <= resp.status < 400:
                return True, latency, None, details
            return False, latency, f'HTTP {resp.status}', details
    except asyncio.TimeoutError:
        return False, 0.0, 'Timeout', details
    except Exception as e:
        return False, 0.0, str(e), details

def ping_host(host: str, count: int = 3):
    import platform
    import re
    try:
        # Windows uses -n for count and -w for timeout (in ms)
        if platform.system().lower() == 'windows':
            result = subprocess.run(['ping', '-n', str(count), '-w', '2000', host], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run(['ping', '-c', str(count), '-W', '2', host], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            output = result.stdout
            # Try Linux format: rtt min/avg/max/mdev
            for line in output.split('\n'):
                if 'avg' in line or 'rtt' in line:
                    parts = line.split('=')
                    if len(parts) >= 2:
                        times = parts[1].strip().split('/')
                        if len(times) >= 2:
                            return True, float(times[1]), None, None
            # Try Windows format: Average = XXms
            match = re.search(r'Average\s*=\s*(\d+)\s*ms', output, re.IGNORECASE)
            if match:
                return True, float(match.group(1)), None, None
            # Windows: look for time=XXms patterns
            times_list = re.findall(r'time[=<](\d+)\s*ms', output, re.IGNORECASE)
            if times_list:
                avg = sum(int(t) for t in times_list) / len(times_list)
                return True, avg, None, None
            return True, 0.0, None, None
        return False, 0.0, 'Host unreachable', None
    except subprocess.TimeoutExpired:
        return False, 0.0, 'Timeout', None
    except Exception as e:
        return False, 0.0, str(e), None

def check_tcp(host: str, port: int, timeout: int = 5):
    start = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        latency = (time.time() - start) * 1000
        sock.close()
        if result == 0:
            return True, latency, None
        return False, latency, f'Connection refused (error: {result})'
    except socket.timeout:
        return False, 0.0, 'Timeout'
    except socket.gaierror as e:
        return False, 0.0, f'DNS resolution failed: {e}'
    except Exception as e:
        return False, 0.0, str(e)

async def check_dns(host: str, dns_server: str = '8.8.8.8'):
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec('dig', '+short', '+time=2', '+tries=1', f'@{dns_server}', host, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        latency = (time.time() - start) * 1000
        if proc.returncode == 0 and stdout.strip():
            return True, latency, None, None
        return False, latency, 'DNS resolution failed', None
    except FileNotFoundError:
        try:
            socket.gethostbyname(host)
            latency = (time.time() - start) * 1000
            return True, latency, None, None
        except socket.gaierror as e:
            return False, 0.0, str(e), None
    except Exception as e:
        return False, 0.0, str(e), None

async def run_cycle(cfg):
    concurrency = cfg.get('concurrency', 6)
    sem = asyncio.Semaphore(concurrency)
    checks = cfg.get('targets', [])
    results = []
    async with aiohttp.ClientSession() as session:
        async def run_target(t):
            async with sem:
                ttype = t.get('type', 'ping')
                host = t.get('host')
                name = t.get('name')
                if ttype == 'http':
                    success, latency, error, details = await check_http(session, host)
                elif ttype == 'ping':
                    success, latency, error, details = await asyncio.to_thread(ping_host, host)
                elif ttype == 'tcp':
                    port = t.get('port', 80)
                    success, latency, error = await asyncio.to_thread(check_tcp, host, port)
                    details = None
                elif ttype == 'dns':
                    dns_server = t.get('dns_server', '8.8.8.8')
                    success, latency, error, details = await check_dns(host, dns_server)
                else:
                    success, latency, error, details = False, 0.0, 'Unknown type', None

                status = 'online' if success and latency <= 500 else ('degraded' if success else 'offline')
                return {
                    'target_name': name,
                    'host': host,
                    'type': ttype,
                    'status': status,
                    'latency_ms': round(latency, 2),
                    'timestamp': utcnow().isoformat(),
                    'error': error,
                    'details': details
                }

        tasks = [run_target(t) for t in checks]
        for fut in asyncio.as_completed(tasks):
            r = await fut
            results.append(r)

    return results

async def send_batch(results):
    url = f"{DISPLAY_URL.rstrip('/')}/api/ingest"
    payload = {'agent_id': AGENT_ID, 'checks': results}
    headers = {'Content-Type': 'application/json', 'X-API-Key': API_KEY}

    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return True
                    text = await resp.text()
                    print(f"Ingest failed: {resp.status} - {text}")
        except Exception as e:
            print(f"Error sending batch: {e}")
        await asyncio.sleep(2 ** attempt)
    return False

async def main_loop(cfg):
    interval = cfg.get('check_interval', 60)
    batch_send_interval = cfg.get('batch_send_interval', 10)
    
    # Wait until the next round minute to start
    now = time.time()
    seconds_into_minute = now % 60
    if seconds_into_minute > 0:
        sleep_time = 60 - seconds_into_minute
        print(f"Waiting {sleep_time:.1f}s to sync with next round minute...")
        await asyncio.sleep(sleep_time)
    
    while True:
        cycle_start = time.time()
        results = await run_cycle(cfg)
        await send_batch(results)
        
        # Calculate sleep time to wake up at the next round minute
        elapsed = time.time() - cycle_start
        sleep_time = interval - (elapsed % interval)
        
        # Adjust to align with round minutes
        now = time.time()
        seconds_into_minute = now % 60
        target_seconds = (60 - seconds_into_minute) if seconds_into_minute > 0 else 60
        
        # Use the target_seconds to sync with round minutes
        await asyncio.sleep(target_seconds)

if __name__ == '__main__':
    cfg_path = Path(CONFIG_PATH)
    if not cfg_path.exists():
        print(f"Config {CONFIG_PATH} not found")
        raise SystemExit(1)

    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    # Allow env overrides
    cfg['check_interval'] = int(os.environ.get('CHECK_INTERVAL', cfg.get('check_interval', 30)))
    asyncio.run(main_loop(cfg))
