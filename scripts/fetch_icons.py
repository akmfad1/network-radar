#!/usr/bin/env python3
"""Fetch icons/favicons for targets defined in config.yaml and save them to static/icons

Behavior:
- If target has `icon` that is a URL, download it and save with its basename.
- If target has `icon` that is a filename, skip downloading but ensure existence (try to fetch favicon if missing).
- If no `icon` provided, attempt to fetch favicon from the target host and save as `<slugified-name>.ico` or detected extension.
"""
import os
import re
import sys
from pathlib import Path
import yaml

try:
    import requests
    have_requests = True
except Exception:
    import urllib.request
    import urllib.parse
    have_requests = False

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'config.yaml'
OUT_DIR = ROOT / 'static' / 'icons'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", '-', s)
    s = re.sub(r"-+", '-', s).strip('-')
    return s or 'icon'


def download_url(url: str, out_path: Path) -> bool:
    print(f"Downloading {url} → {out_path.name}")
    try:
        if have_requests:
            r = requests.get(url, timeout=10, allow_redirects=True)
            if r.status_code == 200 and r.content:
                out_path.write_bytes(r.content)
                return True
            else:
                print(f"Failed to download {url}: status {r.status_code}")
                return False
        else:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = r.read()
                out_path.write_bytes(data)
                return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False


def fetch_favicon_from_host(host: str):
    # host can be host or full URL
    if not host:
        return None
    # ensure scheme
    if not re.match(r'^https?://', host):
        host = 'https://' + host
    try_urls = []
    # primary attempt: /favicon.ico
    base = host.rstrip('/')
    try_urls.append(base + '/favicon.ico')

    # attempt to fetch page and look for <link rel="icon" ...>
    try:
        if have_requests:
            r = requests.get(base, timeout=8)
            text = r.text if r.status_code == 200 else ''
        else:
            with urllib.request.urlopen(base, timeout=8) as r:
                text = r.read().decode('utf-8', errors='ignore')
        # search for link rel icon
        m = re.search(r'<link[^>]+rel=["\'](?:shortcut icon|icon)["\'][^>]*>', text, re.IGNORECASE)
        if m:
            tag = m.group(0)
            href_m = re.search(r'href=["\']([^"\']+)["\']', tag)
            if href_m:
                href = href_m.group(1)
                # make absolute
                href = urllib.parse.urljoin(base + '/', href)
                try_urls.append(href)
    except Exception:
        pass

    # try the URLs
    for u in try_urls:
        try:
            if download_url(u, OUT_DIR / Path(u).name):
                return Path(u).name
        except Exception:
            continue
    return None


def main():
    if not CONFIG_PATH.exists():
        print("config.yaml not found")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}

    targets = cfg.get('targets', [])
    downloaded = []

    for t in targets:
        name = t.get('name')
        host = t.get('host')
        icon = t.get('icon')

        filename = None
        if icon:
            if re.match(r'^https?://', str(icon)):
                # download remote URL
                filename = Path(icon).name
                outp = OUT_DIR / filename
                if not outp.exists():
                    ok = download_url(icon, outp)
                    if ok:
                        downloaded.append(filename)
                else:
                    print(f"Already exists: {outp.name}")
            else:
                # filename given; if missing try to fetch favicon and save as this filename
                outp = OUT_DIR / icon
                if not outp.exists():
                    # try to get favicon from host
                    fetched = fetch_favicon_from_host(host)
                    if fetched:
                        # rename fetched to desired name
                        (OUT_DIR / fetched).replace(outp)
                        downloaded.append(outp.name)
                        filename = outp.name
                    else:
                        print(f"Could not fetch favicon for {name}")
                        filename = None
                else:
                    print(f"Icon already present for {name}: {outp.name}")
                    filename = outp.name
        else:
            # attempt to fetch favicon from host and save with slugified name
            slug = slugify(name)
            # try common extensions .ico or .png
            fetched = fetch_favicon_from_host(host)
            if fetched:
                # rename to slug + ext
                ext = Path(fetched).suffix or '.ico'
                outp = OUT_DIR / (slug + ext)
                (OUT_DIR / fetched).replace(outp)
                downloaded.append(outp.name)
                filename = outp.name
            else:
                print(f"No favicon found for {name} ({host})")

        if filename:
            print(f"Saved icon for {name}: {filename}")

    print("Done. Downloaded:", downloaded)

if __name__ == '__main__':
    main()
