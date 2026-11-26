"""Serve the scan API and the built Vue application."""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from scanner import ScanError, analyze_repository

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/scan":
            return self.send_json(404, {"error": "接口不存在。"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                return self.send_json(413, {"error": "请求内容过大或为空。"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                return self.send_json(400, {"error": "请求格式错误。"})
            report = analyze_repository(data.get("url"))
            self.send_json(200, report)
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"error": "请求格式错误。"})
        except ScanError as error:
            self.send_json(400, {"error": str(error)})
        except Exception:
            self.send_json(500, {"error": "扫描失败，请稍后重试。"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json(200, {"status": "ok"})
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "接口不存在。"})
        if not DIST.exists():
            return self.send_json(503, {"error": "前端尚未构建，请先运行 npm run build。"})
        relative = path.lstrip("/") or "index.html"
        file = (DIST / relative).resolve()
        if not file.is_relative_to(DIST.resolve()) or not file.is_file():
            file = DIST / "index.html"
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(file.name)[0] or "application/octet-stream") + ("; charset=utf-8" if file.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Git 仓库接入体检: http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
