"""主框架只读看板：读 neuron.db，3D 展示记忆与链接，另附遗忘曲线对照。

用法：python -m viewer.server --db data/neuron.db --port 8420
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent


def region_of(note: dict) -> str:
    if note.get("archived") or note.get("superseded_by") is not None:
        return "forgotten"
    if note.get("tier") == "long":
        return "deep"
    ntype = note.get("type")
    if ntype == "chat":
        return "chatter"
    if ntype == "preference":
        return "emotion"
    if ntype in ("decision", "project"):
        return "executive"
    if ntype in ("concept", "skill"):
        return "semantic"
    return "hippocampus"


def load_graph(db: str) -> dict:
    conn = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    notes = [
        dict(r)
        for r in conn.execute(
            "SELECT id, text, type, importance, n_eff, tier, archived, superseded_by, "
            "valid_from, valid_to, created_at, updated_at, last_access, access_count, episode_id, pinned, "
            "(SELECT text FROM episodes e WHERE e.id = notes.episode_id) AS episode_text FROM notes"
        )
    ]
    links = [dict(r) for r in conn.execute("SELECT src, dst, weight, valid_from, valid_to FROM links")]
    events = [
        dict(r)
        for r in conn.execute(
            "SELECT id, ts, kind, text, note_id, meta FROM raw_events ORDER BY id DESC LIMIT 200"
        )
    ]
    conn.close()
    for note in notes:
        note["region"] = region_of(note)
    active = [n for n in notes if not n["archived"] and n["superseded_by"] is None]
    tiers = {"short": 0, "long": 0}
    for n in active:
        tiers[n["tier"]] = tiers.get(n["tier"], 0) + 1
    return {
        "notes": notes,
        "links": links,
        "events": events,
        "stats": {
            "active": len(active),
            "archived": sum(1 for n in notes if n["archived"]),
            "superseded": sum(1 for n in notes if n["superseded_by"] is not None),
            "links": len(links),
            "tiers": tiers,
            "db": str(Path(db).resolve()),
        },
    }


class Handler(BaseHTTPRequestHandler):
    db: str

    def _send(self, code: int, body: str, ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "ui.html").read_text("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/ui3d.html":
            self._send(200, (HERE / "ui3d.html").read_text("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/ui2d.html":
            self._send(200, (HERE / "ui2d.html").read_text("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            try:
                graph = load_graph(Handler.db)
                self._send(200, json.dumps({"ok": True, "notes": len(graph["notes"])}))
            except Exception as exc:  # noqa: BLE001
                self._send(200, json.dumps({"ok": False, "error": str(exc)}))
        elif self.path == "/api/graph":
            self._send(200, json.dumps(load_graph(Handler.db), ensure_ascii=False))
        else:
            self._send(404, "{}")

    def log_message(self, *args) -> None:
        pass


class ViewerServer(ThreadingHTTPServer):
    """Rebind immediately after a restart; launchers check health first."""

    allow_reuse_address = True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/neuron.db")
    ap.add_argument("--port", type=int, default=8420)
    args = ap.parse_args()
    Handler.db = args.db
    if sys.stdout is not None:
        print(f"memory viewer ready: http://127.0.0.1:{args.port}", flush=True)
    ViewerServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
