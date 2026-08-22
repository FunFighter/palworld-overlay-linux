#!/usr/bin/env python3
"""Local server for the Palworld live map overlay.

Serves the map UI and proxies the dedicated-server REST API, so the browser
never sees the admin password. One upstream poll feeds any number of clients.
"""
import base64, json, os, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")

CTYPES = {
    ".html": "text/html; charset=utf-8", ".js": "application/javascript",
    ".css": "text/css", ".png": "image/png", ".webp": "image/webp",
    ".json": "application/json", ".svg": "image/svg+xml",
}


def load_cfg():
    with open(CFG_PATH) as f:
        return json.load(f)


class Poller(threading.Thread):
    """Polls the game server so many browser clients cost one upstream request."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.latest = {"players": [], "ts": 0, "error": None}

    def run(self):
        while True:
            try:
                cfg = load_cfg()
                url = cfg["rest_url"].rstrip("/") + "/v1/api/players"
                auth = base64.b64encode(
                    f"{cfg['rest_user']}:{cfg['rest_pass']}".encode()).decode()
                req = urllib.request.Request(
                    url, headers={"Authorization": "Basic " + auth})
                with urllib.request.urlopen(req, timeout=6) as r:
                    data = json.load(r)
                self.latest = {"players": data.get("players", []),
                               "ts": time.time(), "error": None}
                delay = cfg.get("poll_ms", 1000) / 1000
            except Exception as e:
                self.latest = {"players": self.latest.get("players", []),
                               "ts": self.latest.get("ts", 0),
                               "error": f"{type(e).__name__}: {e}"}
                delay = 2.0
            time.sleep(max(0.25, delay))


POLLER = Poller()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/players":
            out = dict(POLLER.latest)
            out["me"] = load_cfg().get("me")
            return self._json(200, out)
        if path == "/api/config":
            cfg = load_cfg()
            return self._json(200, {"me": cfg.get("me"),
                                    "poll_ms": cfg.get("poll_ms", 1000)})
        if path == "/":
            path = "/index.html"

        full = os.path.realpath(os.path.join(HERE, path.lstrip("/")))
        if not full.startswith(os.path.realpath(HERE)) or not os.path.isfile(full):
            return self._json(404, {"error": "not found"})
        if os.path.basename(full) in ("config.json", "window.json"):
            return self._json(403, {"error": "forbidden"})

        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CTYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # map data and the sprite are content-stable; the UI itself should not cache
        self.send_header("Cache-Control",
                         "public, max-age=86400" if ext in (".png", ".webp", ".js", ".css")
                         else "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    POLLER.start()
    port = load_cfg().get("listen_port", 8765)
    print(f"Palworld live map on http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
