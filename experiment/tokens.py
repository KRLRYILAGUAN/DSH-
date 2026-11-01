"""统计 DSH 会话的 LLM token 用量（只读扫描 ~/.dsh/sessions）。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import zstandard


def _session_files():
    base = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh"))) / "sessions"
    if not base.exists():
        return
    for ws in base.iterdir():
        if not ws.is_dir():
            continue
        for s in ws.iterdir():
            f = s / "session.v4.jsonl.zstd"
            if f.exists():
                yield s.name, f


def scan_sessions() -> dict:
    cur = os.environ.get("DSH_SESSION_ID")
    today = datetime.now().strftime("%Y-%m-%d")
    out = {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
        "sessions": 0,
        "today": {"input": 0, "output": 0},
        "current": {"input": 0, "output": 0},
    }
    for sid, f in _session_files():
        try:
            with open(f, "rb") as fh:
                data = zstandard.ZstdDecompressor().stream_reader(fh).read().decode("utf-8", "ignore")
        except Exception:
            continue
        out["sessions"] += 1
        for line in data.splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            u = (obj.get("data") or {}).get("usage")
            if not u:
                continue
            ts = obj.get("time") or 0
            day = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
            for k, key in (
                ("input", "inputTokens"),
                ("output", "outputTokens"),
                ("cache_read", "cacheReadTokens"),
                ("cache_write", "cacheWriteTokens"),
            ):
                v = u.get(key) or 0
                out[k] += v
                if sid == cur:
                    out["current"][k] = out["current"].get(k, 0) + v
                if day == today:
                    out["today"][k] = out["today"].get(k, 0) + v
    return out
