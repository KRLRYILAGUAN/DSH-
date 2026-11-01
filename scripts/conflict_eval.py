"""冲突检测小评测：新旧记忆对，判断是否应该 supersede。"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder

PAIRS = [
    # (old, new, should_supersede)
    ("喜欢咖啡", "不喜欢咖啡", True),
    ("周五开会", "改到周一开会", True),
    ("预算 1000", "预算 2000", True),
    ("住在北京", "搬到上海", True),
    ("用 Python 写服务", "改用 Rust 写服务", True),
    ("下午三点开会", "改到下午四点开会", True),
    ("要加糖", "不加糖", True),
    ("每周跑步 3 次", "每周跑步 5 次", True),
    ("住在公司附近", "搬到公司对面", True),
    ("项目负责人是张三", "项目负责人换成李四", True),
    ("不支持方案 A", "支持方案 A", True),
    ("喜欢咖啡", "喜欢加糖的咖啡", False),
    ("周五开会", "周五开会带电脑", False),
    ("住在北京", "北京天气很好", False),
    ("预算 1000", "预算 1000 包含税", False),
    ("用 Python 写服务", "用 Python 写脚本", False),
    ("下午三点开会", "下午三点开会半小时", False),
    ("每周跑步 3 次", "跑步有益健康", False),
    ("项目负责人是张三", "张三负责测试", False),
    ("不喜欢咖啡", "不讨厌咖啡", False),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default="fastembed")
    args = ap.parse_args()
    emb = get_embedder(args.embedder)
    tmp = Path(tempfile.mkdtemp(prefix="conflict_"))
    tp = fp = fn = tn = 0
    for i, (old, new, expect) in enumerate(PAIRS):
        db = tmp / f"c{i}.db"
        mem = NeuronMemory(str(db), embedder=emb)
        mem.remember(old, importance=0.6)
        mem.remember(new, importance=0.6)
        rows = mem.store.all_notes(include_superseded=True)
        old_row = next((r for r in rows if r["text"] == old), None)
        if old_row is None:
            old_row = next((r for r in rows if old in r["text"] or r["text"] in old), None)
        if old_row is None:
            print(f"??  {old!r} + {new!r} (merged/removed)")
            fn += 1 if expect else 0
            continue
        got = old_row["superseded_by"] is not None
        if got and expect:
            tp += 1
        elif got and not expect:
            fp += 1
            print(f"FP  {old!r} + {new!r}")
        elif not got and expect:
            fn += 1
            print(f"FN  {old!r} + {new!r}")
        else:
            tn += 1
        mem.store.close() if hasattr(mem.store, "close") else None
    total = len(PAIRS)
    print(f"embedder={emb.name} total={total} TP={tp} FP={fp} FN={fn} TN={tn} accuracy={(tp+tn)/total:.3f}")


if __name__ == "__main__":
    main()
