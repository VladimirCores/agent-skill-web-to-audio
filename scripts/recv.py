#!/usr/bin/env python3
"""Receive JSON posted by a browser page and save it under OUT/<name>.json.

Usage: python3 recv.py [port] [out_dir]
Cross-origin headers let an HTTPS lesson page POST to this loopback receiver.
"""
import argparse, json, pathlib, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('port', nargs='?', type=int, default=8765)
ap.add_argument('out_dir', nargs='?', default='.')
args = ap.parse_args()
PORT = args.port
OUT = pathlib.Path(args.out_dir).resolve()
OUT.mkdir(parents=True, exist_ok=True)


class H(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Private-Network', 'true')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/save':
            self.send_error(404)
            return
        name = (parse_qs(u.query).get('name') or ['dump'])[0]
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', name)
        size = int(self.headers.get('Content-Length') or 0)
        try:
            data = json.loads(self.rfile.read(size).decode('utf-8'))
        except Exception as exc:
            self.send_response(400)
            self._cors()
            self.end_headers()
            self.wfile.write(str(exc).encode())
            return
        (OUT / (name + '.json')).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    print(f'Receiver on http://127.0.0.1:{PORT}/save -> {OUT}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
