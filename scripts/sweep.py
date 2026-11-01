"""参数扫描：在固定评测集上比较不同打分权重配置（fastembed 后端）。

用法：.venv\\Scripts\\python -m scripts.sweep
"""

from __future__ import annotations

from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder
from scripts.eval import QUERIES, SEEDS

CONFIGS = {
    "A_default": dict(weights={"sim": 0.50, "imp": 0.12, "rec": 0.08, "freq": 0.05, "lex": 0.15}, floor=0.20, span=0.60, hop=0.25),
    "B_sim_heavy": dict(weights={"sim": 0.55, "imp": 0.10, "rec": 0.06, "freq": 0.04, "lex": 0.10}, floor=0.20, span=0.60, hop=0.20),
    "C_lex_heavy": dict(weights={"sim": 0.45, "imp": 0.15, "rec": 0.10, "freq": 0.05, "lex": 0.20}, floor=0.20, span=0.60, hop=0.25),
    "D_hop35": dict(weights={"sim": 0.50, "imp": 0.12, "rec": 0.08, "freq": 0.05, "lex": 0.15}, floor=0.20, span=0.60, hop=0.35),
    "E_pure_sim": dict(weights={"sim": 0.62, "imp": 0.08, "rec": 0.05, "freq": 0.03, "lex": 0.08}, floor=0.20, span=0.60, hop=0.20),
    "F_no_lex": dict(weights={"sim": 0.60, "imp": 0.12, "rec": 0.08, "freq": 0.05, "lex": 0.0}, floor=0.20, span=0.60, hop=0.20),
}


def run_cfg(name: str, cfg: dict) -> dict:
    db = Path(f"data/sweep_{name}.db")
    db.unlink(missing_ok=True)
    mem = NeuronMemory(str(db), embedder=get_embedder("fastembed"))
    mem.weights = cfg["weights"]
    mem.sim_floor, mem.sim_span = cfg["floor"], cfg["span"]
    mem.hop_decay = cfg["hop"]
    ids = [mem.remember(t, ty, imp)[0] for t, ty, imp in SEEDS]
    hit1 = hit3 = 0
    rr = 0.0
    for query, expected in QUERIES:
        rows = mem.recall(query, k=5)
        rank = next((i + 1 for i, r in enumerate(rows) if r["id"] == ids[expected]), None)
        if rank == 1:
            hit1 += 1
        if rank and rank <= 3:
            hit3 += 1
        if rank:
            rr += 1.0 / rank
    n = len(QUERIES)
    return {"hit@1": hit1 / n, "hit@3": hit3 / n, "mrr@5": rr / n}


def main() -> None:
    results = []
    for name, cfg in CONFIGS.items():
        r = run_cfg(name, cfg)
        results.append((name, r))
        print(f"{name:12s} hit@1={r['hit@1']:.3f} hit@3={r['hit@3']:.3f} mrr@5={r['mrr@5']:.3f}")
    best = max(results, key=lambda x: (x[1]["hit@1"], x[1]["mrr@5"]))
    print(f"\nbest: {best[0]}")


if __name__ == "__main__":
    main()
