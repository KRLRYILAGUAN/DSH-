"""LoCoMo cross-encoder 重排实验：先召回 top-N，再用 reranker 取 top-k。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from fastembed.rerank.cross_encoder import TextCrossEncoder

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder
from scripts.locomo_eval import CATS, turns_from


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/locomo10.json")
    ap.add_argument("--embedder", default="fastembed")
    ap.add_argument("--reranker", default="BAAI/bge-reranker-base")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--candidates", type=int, default=30)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--only-cat", type=int, default=1)
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text("utf-8"))[: args.limit]
    emb = get_embedder(args.embedder)
    reranker = TextCrossEncoder(args.reranker, cache_dir="data/models_rerank")
    tmpdir = Path("data/locomo_tmp_rerank")
    tmpdir.mkdir(exist_ok=True)

    ranks: list[int | None] = []
    per_cat: dict[int, list[int]] = {}
    t0 = time.time()
    for si, sample in enumerate(data):
        db = tmpdir / f"s{si}.db"
        db.unlink(missing_ok=True)
        mem = NeuronMemory(str(db), embedder=emb, reranker=reranker)
        turns = turns_from(sample)
        texts = [t[1] for t in turns]
        if hasattr(emb, "model"):
            vecs = list(emb.model.embed(texts))
        else:
            vecs = [emb.embed(t) for t in texts]
        dia_map: dict[str, int] = {}
        for (dia, text, date), vec in zip(turns, vecs):
            nid = mem.store.insert_note(text, "utterance", 0.5)
            mem.store.set_embedding(nid, vec.tolist() if hasattr(vec, "tolist") else vec)
            if date:
                mem.store.conn.execute("UPDATE notes SET valid_from = ? WHERE id = ?", (date, nid))
            dia_map[dia] = nid
        mem.store.conn.commit()

        for qa in sample["qa"]:
            cat = qa.get("category", 0)
            if args.only_cat and cat != args.only_cat:
                continue
            rows = mem.recall(qa["question"], args.k, rerank=True)
            ids = [r["id"] for r in rows]
            ev = {dia_map[e] for e in qa.get("evidence", []) if e in dia_map}
            rank = next((i + 1 for i, rid in enumerate(ids) if rid in ev), None)
            ranks.append(rank)
            per_cat.setdefault(cat, []).append(1 if rank else 0)

    n = len(ranks)
    hit = lambda t: sum(1 for r in ranks if r is not None and r <= t) / n if n else 0.0
    mrr = sum(1 / r for r in ranks if r) / n if n else 0.0
    print(
        f"样本={len(data)} QA={n} 用时={time.time() - t0:.1f}s "
        f"embedder={emb.name} reranker={args.reranker} cand={args.candidates}"
    )
    print(f"检索命中: @1={hit(1):.3f} @3={hit(3):.3f} @5={hit(5):.3f} @{args.k}={hit(args.k):.3f} MRR={mrr:.3f}")
    for cat, vals in sorted(per_cat.items()):
        print(f"  {CATS.get(cat, cat):<4} n={len(vals):<4} 命中={sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    main()
