#!/usr/bin/env python3
"""Zero-dependency dev server for frontend/.

Serves static files from this directory and proxies /api/* to the live vox
backend, keeping the page and API on one origin (avoids CORS — server.py
has no CORS layer).

Usage:
    python3 dev_proxy.py [--port 8080] [--target http://100.64.0.2:7878]

Then open http://localhost:8080/ — localhost is the one non-HTTPS origin
where browsers permit getUserMedia (surface doc §1). WebRTC media itself
flows browser→bot directly, not through this proxy; run from a machine
that can reach the target (prtr or any tailnet node).
"""

import argparse
import functools
import http.server
import os
import urllib.error
import urllib.request


class DevHandler(http.server.SimpleHTTPRequestHandler):
    target = "http://100.64.0.2:7878"

    def do_POST(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def _proxy(self):
        if not self.path.startswith("/api/"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(
            self.target + self.path,
            data=body,
            method=self.command,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                self._relay(res.status, res.headers.get("Content-Type", "application/json"), res.read())
        except urllib.error.HTTPError as e:
            self._relay(e.code, "application/json", e.read())
        except OSError as e:
            self._relay(502, "text/plain", f"proxy error: {e}".encode())

    def _relay(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--target", default=DevHandler.target)
    args = ap.parse_args()
    DevHandler.target = args.target

    here = os.path.dirname(os.path.abspath(__file__))
    handler = functools.partial(DevHandler, directory=here)
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
