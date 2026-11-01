"""只读桥接：把 DSH 记忆库（C:\\Users\\Lenovo\\.memory）里的 markdown 事实导入 neuron_memory。

- 只读源目录，不写回
- 幂等：文本已存在则跳过
- 导入时在 raw_events 记一条 bridge 记录（含来源文件）
"""

from __future__ import annotations

import re
from pathlib import Path

from .memory import NeuronMemory

SKIP_NAMES = {"SOUL.md", "MEMORY.md", "BOOTSTRAP.md", "index.md", "log.md"}


def _clean(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


def _facts_from(path: Path) -> list[str]:
    text = path.read_text("utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) > 2:
            text = parts[2]
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    facts = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if not m:
            continue
        raw = m.group(1)
        if "](" in raw:
            continue  # 跳过「相关页面」链接行
        fact = _clean(raw)
        if not fact or fact.startswith("（") or fact.startswith("_") or fact.startswith("["):
            continue
        if "](" in fact:
            continue
        facts.append(fact)
    return facts


def _importance(rel: str) -> float:
    if rel.startswith("user/"):
        return 0.85
    if rel.startswith("decisions/"):
        return 0.7
    if rel.startswith("projects/"):
        return 0.65
    if rel.startswith("skills/"):
        return 0.6
    return 0.5


def import_memory(mem: NeuronMemory, memory_dir: str | Path, dry_run: bool = False) -> dict:
    memory_dir = Path(memory_dir)
    if not memory_dir.exists():
        raise FileNotFoundError(f"记忆目录不存在: {memory_dir}")
    seen = {r["text"] for r in mem.store.all_notes()}
    stats = {"files": 0, "facts": 0, "imported": 0, "skipped": 0}
    for path in sorted(memory_dir.rglob("*.md")):
        rel = path.relative_to(memory_dir).as_posix()
        if path.name in SKIP_NAMES or rel.startswith("raw/"):
            continue
        stats["files"] += 1
        for fact in _facts_from(path):
            stats["facts"] += 1
            if fact in seen:
                stats["skipped"] += 1
                continue
            if not dry_run:
                nid, _ = mem.remember(fact, "fact", _importance(rel))
                mem.store.record_raw("bridge", fact, nid, {"file": rel})
            seen.add(fact)
            stats["imported"] += 1
    return stats
