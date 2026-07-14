
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
PORT = 8787

if not API_KEY:
    print("WARNING: ANTHROPIC_API_KEY is not set in your environment.")
    print("Run:  export ANTHROPIC_API_KEY=sk-ant-...   before starting this proxy.\n")


class ProxyHandler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path != "/v1/messages":
            self.send_response(404)
            self._cors_headers()
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY or "",
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            status = e.code

        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp_body)

    def log_message(self, fmt, *args):
        print("[proxy]", fmt % args)


if __name__ == "__main__":
    print(f"Proxy listening on http://localhost:{PORT}")
    print("Point live_pipeline_demo.html's callClaude() fetch URL at "
          f"http://localhost:{PORT}/v1/messages, then reload the HTML in your browser.\n")
    HTTPServer(("localhost", PORT), ProxyHandler).serve_forever()
