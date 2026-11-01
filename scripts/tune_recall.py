"""在 LoCoMo 子集上快速调参：权重组合 + 查询扩展（伪相关反馈）。

用法：
  NEURON_MODEL=BAAI/bge-small-en-v1.5 python -m scripts.tune_recall
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder

from .locomo_eval import turns_from

CONFIGS = {
    "A_current": dict(sim=0.35, bm25=0.25, ent=0.08, S=0.10, rec=0.05, lex=0.12, time=0.05),
    "F_hop40": dict(sim=0.35, bm25=0.25, ent=0.08, S=0.10, rec=0.05, lex=0.12, time=0.05, hop=0.4, seeds=5),
    "G_hop60": dict(sim=0.35, bm25=0.25, ent=0.08, S=0.10, rec=0.05, lex=0.12, time=0.05, hop=0.6, seeds=5),
}
SAMPLES = 3


def build_sample(si: int, sample: dict, emb, tmpdir: Path):
    db = tmpdir / f"tune_{si}.db"
    db.unlink(missing_ok=True)
    mem = NeuronMemory(str(db), embedder=emb)
    turns = turns_from(sample)
    texts = [t[1] for t in turns]
    if hasattr(emb, "model"):
        vecs = list(emb.model.embed(texts))
    else:
        vecs = [emb.embed(t) for t in texts]
    dia_map = {}
    for (dia, text, date), vec in zip(turns, vecs):
        nid = mem.store.insert_note(text, "utterance", 0.5)
        mem.store.set_embedding(nid, vec.tolist() if hasattr(vec, "tolist") else vec)
        if date:
            mem.store.conn.execute("UPDATE notes SET valid_from = ? WHERE id = ?", (date, nid))
        dia_map[dia] = nid
    mem.store.conn.commit()
    return mem, dia_map


def run_eval(mem, dia_map, qas, weights: dict, expand: bool = False, split: bool = False):
    w = {k: v for k, v in weights.items() if k in ("sim", "bm25", "ent", "S", "rec", "lex", "time")}
    mem.weights = w
    if "hop" in weights:
        mem.hop_decay = weights["hop"]
    if "seeds" in weights:
        mem.expand_seeds = weights["seeds"]
    ranks = []
    for qa in qas:
        q = qa["question"]
        rows = mem.recall(q, 10)
        if split:
            low = q.lower()
            cut = None
            for marker in (" after ", " before ", " while ", " then "):
                i = low.find(marker)
                if i != -1:
                    cut = (i, i + len(marker))
                    break
            if cut:
                parts = [q[: cut[0]], q[cut[1] :]]
                merged = {r["id"]: r["score"] for r in rows}
                for p in parts[1:]:
                    for r in mem.recall(p, 10):
                        merged[r["id"]] = max(merged.get(r["id"], 0.0), r["score"])
                ids = sorted(merged, key=merged.get, reverse=True)[:10]
            else:
                ids = [r["id"] for r in rows]
        elif expand and rows:
            q2 = q + " " + " ".join(r["text"] for r in rows[:2])
            rows2 = mem.recall(q2, 10)
            merged = {r["id"]: r["score"] for r in rows2}
            for r in rows:
                merged[r["id"]] = max(merged.get(r["id"], 0.0), r["score"])
            ids = sorted(merged, key=merged.get, reverse=True)[:10]
        else:
            ids = [r["id"] for r in rows]
        ev = {dia_map[e] for e in qa.get("evidence", []) if e in dia_map}
        rank = next((i + 1 for i, rid in enumerate(ids) if rid in ev), None)
        ranks.append((qa.get("category"), rank))
    n = len(ranks)
    hit10 = sum(1 for _, r in ranks if r and r <= 10) / n
    mrr = sum(1 / r for _, r in ranks if r) / n
    mh = [r for c, r in ranks if c == 1]
    mh_hit = sum(1 for r in mh if r and r <= 10) / len(mh) if mh else 0.0
    return {"hit@10": round(hit10, 3), "mrr": round(mrr, 3), "multihop": round(mh_hit, 3), "n": n}


def main() -> None:
    data = json.loads(Path("data/locomo10.json").read_text("utf-8"))[:SAMPLES]
    emb = get_embedder("fastembed")
    tmpdir = Path("data/tune_tmp")
    tmpdir.mkdir(exist_ok=True)
    built = []
    for si, sample in enumerate(data):
        mem, dia_map = build_sample(si, sample, emb, tmpdir)
        built.append((mem, dia_map, sample["qa"]))
        print(f"built sample {si}: {len(sample['qa'])} QA")

    for name, w in CONFIGS.items():
        t0 = time.time()
        agg = {"hit@10": [], "mrr": [], "multihop": []}
        for mem, dia_map, qas in built:
            r = run_eval(mem, dia_map, qas, w)
            agg["hit@10"].append(r["hit@10"])
            agg["mrr"].append(r["mrr"])
            agg["multihop"].append(r["multihop"])
        avg = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
        print(f"{name:<12} hit@10={avg['hit@10']:.3f} mrr={avg['mrr']:.3f} multihop={avg['multihop']:.3f} ({time.time()-t0:.0f}s)")

    # 查询扩展对照（用当前权重）
    t0 = time.time()
    agg = {"hit@10": [], "mrr": [], "multihop": []}
    for mem, dia_map, qas in built:
        r = run_eval(mem, dia_map, qas, CONFIGS["A_current"], expand=True)
        agg["hit@10"].append(r["hit@10"])
        agg["mrr"].append(r["mrr"])
        agg["multihop"].append(r["multihop"])
    avg = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
    print(f"{'E_expand':<12} hit@10={avg['hit@10']:.3f} mrr={avg['mrr']:.3f} multihop={avg['multihop']:.3f} ({time.time()-t0:.0f}s)")

    t0 = time.time()
    agg = {"hit@10": [], "mrr": [], "multihop": []}
    for mem, dia_map, qas in built:
        r = run_eval(mem, dia_map, qas, CONFIGS["A_current"], split=True)
        agg["hit@10"].append(r["hit@10"])
        agg["mrr"].append(r["mrr"])
        agg["multihop"].append(r["multihop"])
    avg = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
    print(f"{'H_split':<12} hit@10={avg['hit@10']:.3f} mrr={avg['mrr']:.3f} multihop={avg['multihop']:.3f} ({time.time()-t0:.0f}s)")

    for mem, dia_map, qas in built:
        mem.build_entity_links()
    t0 = time.time()
    agg = {"hit@10": [], "mrr": [], "multihop": []}
    for mem, dia_map, qas in built:
        r = run_eval(mem, dia_map, qas, CONFIGS["A_current"])
        agg["hit@10"].append(r["hit@10"])
        agg["mrr"].append(r["mrr"])
        agg["multihop"].append(r["multihop"])
    avg = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
    print(f"{'I_entity':<12} hit@10={avg['hit@10']:.3f} mrr={avg['mrr']:.3f} multihop={avg['multihop']:.3f} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
