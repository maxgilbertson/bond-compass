"""Bond Compass: a live tracker of the world's government bond markets.

Run:  py app/server.py   then open http://localhost:8766   (add --lan to reach it from phones on your Wi-Fi)
Data is rebuilt at most every CACHE_SECONDS so open pages can poll without hammering the sources.
"""
import json
import math
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import bonds
import markets

PORT = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8766)
CACHE_SECONDS = 300
HERE = Path(__file__).parent
PAGES = {"index.html", "common.css", "common.js"}  # the files the site is made of
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".json": "application/json", ".md": "text/markdown; charset=utf-8"}
CODES = {m[0] for m in markets.MARKETS}

_cache = {"at": 0, "body": None}
_lock = threading.Lock()


def clean(o):
    """Make a structure JSON-safe (NaN and infinity become null)."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def dumps(o):
    return json.dumps(clean(o), separators=(",", ":"), allow_nan=False).encode()


def get_data(force=False):
    with _lock:
        if force or not _cache["body"] or time.time() - _cache["at"] > CACHE_SECONDS:
            t0 = time.time()
            data = bonds.build()
            data["buildSeconds"] = round(time.time() - t0, 1)
            _cache["body"], _cache["at"] = dumps(data), time.time()
            print(f"[{datetime.now():%H:%M:%S}] refreshed {len(data['rows'])} markets in {data['buildSeconds']}s; "
                  f"problems: {data['errors'] or 'none'}", flush=True)
        return _cache["body"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        try:
            name = u.path.strip("/") or "index.html"
            if name in ("api/bonds", "api/bonds.json"):
                self._send(200, get_data(force="force" in parse_qs(u.query)), "application/json")
            elif name.startswith("api/hist/"):
                code = name[9:].removesuffix(".json").upper()
                if code not in CODES:
                    return self._send(404, b"not found", "text/plain")
                self._send(200, dumps(bonds.country_history(code)), "application/json")
            elif name.startswith("briefings/") and ".." not in name and Path(name).suffix in (".json", ".md") \
                    and (HERE.parent / "data" / name).is_file():
                self._send(200, (HERE.parent / "data" / name).read_bytes(), TYPES[Path(name).suffix])
            elif name in PAGES:
                self._send(200, (HERE / name).read_bytes(), TYPES[Path(name).suffix])
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    if "--check" in sys.argv:
        d = json.loads(get_data())
        print("markets", len(d["rows"]), "problems", d["errors"])
        sys.exit()
    lan = "--lan" in sys.argv  # also serve other devices on the same Wi-Fi (e.g. your phone)
    print(f"Bond Compass running at http://localhost:{PORT}  (Ctrl+C to stop)", flush=True)
    if lan:
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))  # no packets sent; just picks the Wi-Fi interface
                ip = s.getsockname()[0]
            print(f"\n  On your phone (same Wi-Fi), open:  http://{ip}:{PORT}\n", flush=True)
        except OSError:
            print("  Could not detect this PC's network address; run ipconfig to find it.", flush=True)
    threading.Thread(target=get_data, daemon=True).start()  # warm the cache
    ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", PORT), Handler).serve_forever()
