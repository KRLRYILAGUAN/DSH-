"""导出单文件看板快照：viewer/snapshot.html，双击即可打开（数据不刷新）。"""

from __future__ import annotations

import json
from pathlib import Path

from viewer.server import load_graph


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    g = load_graph(str(root / "data" / "neuron.db"))
    html = (root / "viewer" / "ui.html").read_text("utf-8")
    body = json.dumps(g, ensure_ascii=False).replace("</", "<\\/")
    inject = "<script>window.__GRAPH__ = " + body + ";</script>"
    html = html.replace("<script>", inject + "\n<script>", 1)
    out = root / "viewer" / "snapshot.html"
    out.write_text(html, "utf-8")
    print(f"snapshot written: {out} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
