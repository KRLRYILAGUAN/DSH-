"""实验台 HTTP 服务：托管可视化页面 + 状态 API（标准库，无外部依赖）。

用法：python -m experiment.server --port 8410
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import Experiment

HERE = Path(__file__).resolve().parent
STATE = HERE / "data" / "state.json"
_TOKEN_CACHE = {"t": 0.0, "data": None}


class Handler(BaseHTTPRequestHandler):
    experiment: Experiment

    def _send(self, code: int, body: str | bytes, ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "ui.html").read_text("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(self.experiment.state_view(), ensure_ascii=False))
        elif self.path.startswith("/api/history"):
            q = parse_qs(urlparse(self.path).query)
            mid = int((q.get("id") or ["0"])[0])
            hist = (self.experiment.data or {}).get("history", [])
            series = [[h[0], h[2]] for h in hist if h[1] == mid]
            self._send(200, json.dumps({"id": mid, "series": series}, ensure_ascii=False))
        elif self.path == "/api/export.csv":
            st = self.experiment.state_view()
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["id", "kind", "cluster", "n", "state", "S", "B", "text", "short"])
            for m in st["memories"]:
                writer.writerow([m["id"], m["kind"], m.get("cluster", 0), m["n"], m["state"], m["S"], m["B"], m["text"], m["short"] or ""])
            self._send(200, "\ufeff" + buf.getvalue(), "text/csv; charset=utf-8")
        elif self.path == "/api/tokens":
            now = time.time()
            if now - _TOKEN_CACHE["t"] > 30 or _TOKEN_CACHE["data"] is None:
                from .tokens import scan_sessions

                _TOKEN_CACHE["data"] = scan_sessions()
                _TOKEN_CACHE["t"] = now
            self._send(200, json.dumps(_TOKEN_CACHE["data"], ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            payload = {}
        if self.path == "/api/start":
            self.experiment.start(
                float(payload.get("speed", 1.0)), bool(payload.get("demo", False))
            )
            self._send(200, json.dumps(self.experiment.state_view(), ensure_ascii=False))
        elif self.path == "/api/mention":
            ok, msg = self.experiment.mention(
                int(payload.get("id", -1)), str(payload.get("source", "user"))
            )
            body = {"ok": ok, "msg": msg, "state": self.experiment.state_view()}
            self._send(200, json.dumps(body, ensure_ascii=False))
        elif self.path == "/api/reset":
            self.experiment.reset()
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, "{}")

    def log_message(self, *args) -> None:  # 安静运行
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8410)
    ap.add_argument("--state", default=str(STATE))
    args = ap.parse_args()
    Handler.experiment = Experiment(Path(args.state))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"memory experiment ready: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
