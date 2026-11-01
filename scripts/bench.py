"""检索性能基准：numpy 向量化 + 向量缓存 + SQL 索引。

用法：python -m scripts.bench
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.memory import _iso, _now

N = 3000


def main() -> None:
    p = Path("data/bench.db")
    p.unlink(missing_ok=True)
    m = NeuronMemory(str(p))
    now = _iso(_now())
    conn = m.store.conn
    t0 = time.time()
    for i in range(N):
        text = f"合成记忆 {i}：性能测试占位文本，用于验证向量检索速度"
        vec = m.embedder.embed(text)
        conn.execute(
            "INSERT INTO notes (text, type, importance, created_at, updated_at, n_eff, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (text, "fact", 0.5, now, now, 1.0, json.dumps(vec)),
        )
    conn.commit()
    print(f"插入 {N} 条: {time.time() - t0:.1f}s")

    for label in ("cold", "warm"):
        if label == "cold":
            m.store._vec_cache.clear()
        t = time.time()
        rows = m.recall("占位文本 12", 10)
        print(f"recall {label}: {(time.time() - t) * 1000:.1f} ms  (top={rows[0]['id'] if rows else '-'})")
    p.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
