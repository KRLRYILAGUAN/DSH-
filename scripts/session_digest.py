"""离线会话抽取：扫描 DSH 会话记录，把用户说过的稳定事实写入 neuron-memory。

默认 dry-run，只打印候选；--apply 才写库。
只读本工作区的会话（按记录头里的 cwd 判断），不碰其他工作区。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import zstandard

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder
from neuron_memory.memory import cosine

CUE = re.compile(r"我|喜欢|讨厌|偏好|习惯|决定|以后|记住|不要|别|计划|项目|住|吃|喝|预算|名字|叫")
QUESTION = re.compile(r"[?？]$|吗$|呢$")
CODE = re.compile(r"^(\$|>|```|http|/|--|import |def |class )")


def message_text(obj: dict) -> str:
    data = obj.get("data") or {}
    parts = data.get("content")
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    out = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(str(part.get("text") or ""))
    return "\n".join(out)


def candidates(text: str) -> list[str]:
    out = []
    for raw in re.split(r"[\n。！？!?；;]", text):
        s = raw.strip()
        if not (8 <= len(s) <= 200):
            continue
        if CODE.search(s) or QUESTION.search(s):
            continue
        if not CUE.search(s):
            continue
        out.append(s)
    return out


def session_cwd(path: Path) -> str:
    try:
        with path.open("rb") as f:
            head = zstandard.ZstdDecompressor().stream_reader(f).read(4000)
        first = head.decode("utf-8", "ignore").splitlines()[0]
        return json.loads(first).get("cwd") or ""
    except Exception:
        return ""


def iter_user_messages(path: Path):
    with path.open("rb") as f:
        data = zstandard.ZstdDecompressor().stream_reader(f).read()
    for line in data.decode("utf-8", "ignore").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "user/message":
            continue
        src = (obj.get("data") or {}).get("source") or {}
        if isinstance(src, dict) and src.get("kind") != "user":
            continue
        yield message_text(obj)


def main() -> None:
    ap = argparse.ArgumentParser()
    default_ws = Path(__file__).resolve().parents[2]
    ap.add_argument("--workspace", default=str(default_ws))
    ap.add_argument("--db", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--recent", type=int, default=0, help="只输出最近 N 个会话的用户消息（JSON），供 agent 判断")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve()
    db = Path(args.db) if args.db else workspace / ".neuron-memory" / "neuron.db"
    state_path = db.parent / "digest_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text("utf-8"))
    else:
        state = {}

    sessions = Path.home() / ".dsh" / "sessions"
    files = sorted(sessions.glob("*/*/session.v4.jsonl.zstd"), key=lambda p: p.stat().st_mtime, reverse=True)

    if args.recent:
        picked = []
        used = 0
        for path in files:
            if used >= args.recent:
                break
            cwd = session_cwd(path)
            if not cwd or Path(cwd).resolve() != workspace:
                continue
            used += 1
            for text in iter_user_messages(path):
                text = " ".join(text.split())
                if len(text) < 2:
                    continue
                picked.append({"session": path.parent.name, "text": text[:500]})
        print(json.dumps(picked[-60:], ensure_ascii=False, indent=2))
        return

    mem = NeuronMemory(str(db), embedder=get_embedder())
    existing = mem.store.all_notes()
    existing_vecs = [(r["id"], r["vec"]) for r in existing if r.get("vec")]

    picked: list[tuple[str, str]] = []
    scanned = 0
    for path in files[: args.limit]:
        cwd = session_cwd(path)
        if not cwd or Path(cwd).resolve() != workspace:
            continue
        key = str(path)
        sig = {"size": path.stat().st_size, "mtime": int(path.stat().st_mtime)}
        if state.get(key) == sig:
            continue
        scanned += 1
        seen = set()
        for text in iter_user_messages(path):
            for cand in candidates(text):
                if cand in seen:
                    continue
                seen.add(cand)
                vec = mem.embedder.embed(cand)
                if any(cosine(vec, v) >= 0.92 for _, v in existing_vecs):
                    continue
                picked.append((cand, key))
                existing_vecs.append((-1, vec))
        state[key] = sig

    print(f"workspace={workspace} scanned_sessions={scanned} candidates={len(picked)} db={db}")
    staging = db.parent / "digest_candidates.jsonl"
    with staging.open("w", encoding="utf-8") as fh:
        for text, src in picked:
            fh.write(json.dumps({"text": text, "session": src}, ensure_ascii=False) + "\n")
    print(f"staging={staging}")
    for text, _ in picked[:20]:
        print(" -", text[:80])
    if not args.apply:
        print("dry-run: 没有写库（加 --apply 才写入）")
        return

    added = 0
    for text, _ in picked:
        ntype = "preference" if re.search(r"喜欢|讨厌|偏好|习惯", text) else (
            "decision" if re.search(r"决定|以后|计划|不要|别", text) else "fact"
        )
        _, mode = mem.remember(text, ntype, 0.7)
        if mode in ("created", "merged"):
            added += 1
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
    print(f"applied: {added} candidates -> {db}")


if __name__ == "__main__":
    main()
