"""LoCoMo 检索评测：把对话 turn 存成记忆，看 QA 的 evidence 是否被召回。

注意：这是「检索召回」评测，不调用 LLM 生成答案，不能与 Mem0 的 LoCoMo 得分直接比较。

用法：
  python -m scripts.locomo_eval --limit 2 --embedder fastembed
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder

CATS = {1: "多跳", 2: "时间", 3: "开放域", 4: "单跳", 5: "对抗"}


def parse_date(s: str) -> str | None:
    if not s:
        return None
    for fmt in ("%I:%M %p on %d %B, %Y", "%d %B, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


def turns_from(sample: dict) -> list[tuple[str, str, str | None]]:
    conv = sample["conversation"]
    out = []
    i = 1
    while f"session_{i}" in conv:
        date = parse_date(conv.get(f"session_{i}_date_time", ""))
        for t in conv[f"session_{i}"]:
            out.append((t["dia_id"], f"{t['speaker']}: {t['text']}", date))
        i += 1
    return out


def split_query(question: str) -> list[str]:
    """Rule-based decomposition: keep the full query plus clause-level queries."""
    parts = re.split(
        r"\b(?:and|after|before|while|then|but|because|so|when)\b|[?,;]",
        question,
        flags=re.IGNORECASE,
    )
    clauses = [p.strip() for p in parts if len(p.strip()) >= 3]
    if not clauses:
        return [question]
    return [question] + clauses[:3]


def entity_queries(question: str) -> list[str]:
    """Entity-anchored expansion: original query (weighted twice) + proper nouns."""
    stop = {
        "what", "when", "where", "who", "why", "how", "did", "does", "was", "were",
        "has", "have", "had", "the", "and", "but", "for", "with", "from", "that",
        "this", "they", "their", "there", "which", "would", "could", "should",
    }
    ents = re.findall(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b", question)
    ents = [e for e in dict.fromkeys(ents) if len(e) >= 3 and e.lower() not in stop]
    if not ents:
        return [question]
    return [question, question] + ents[:4]


def recall_rrf(mem: NeuronMemory, queries: list[str], k: int) -> list[dict]:
    """Reciprocal-rank fusion over multiple query variants."""
    scores: dict[int, float] = {}
    order: dict[int, int] = {}
    for qi, query in enumerate(queries):
        for rank, row in enumerate(mem.recall(query, k)):
            nid = row["id"]
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (60 + rank + 1)
            order.setdefault(nid, qi * 1000 + rank)
    ranked = sorted(scores, key=lambda nid: (-scores[nid], order[nid]))[:k]
    out = []
    for nid in ranked:
        rec = mem.store.get(nid)
        if rec is not None:
            out.append(rec)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/locomo10.json")
    ap.add_argument("--embedder", default="fastembed")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--mode", choices=["baseline", "multi", "entity"], default="baseline")
    ap.add_argument("--only-cat", type=int, default=0)
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text("utf-8"))[: args.limit]
    emb = get_embedder(args.embedder)
    tmpdir = Path("data/locomo_tmp")
    tmpdir.mkdir(exist_ok=True)

    ranks: list[int | None] = []
    per_cat: dict[int, list[int]] = {}
    t0 = time.time()
    for si, sample in enumerate(data):
        db = tmpdir / f"s{si}.db"
        db.unlink(missing_ok=True)
        mem = NeuronMemory(str(db), embedder=emb)
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
            if args.mode == "multi":
                rows = recall_rrf(mem, split_query(qa["question"]), args.k)
            elif args.mode == "entity":
                rows = recall_rrf(mem, entity_queries(qa["question"]), args.k)
            else:
                rows = mem.recall(qa["question"], args.k)
            ids = [r["id"] for r in rows]
            ev = {dia_map[e] for e in qa.get("evidence", []) if e in dia_map}
            rank = next((i + 1 for i, rid in enumerate(ids) if rid in ev), None)
            ranks.append(rank)
            per_cat.setdefault(cat, []).append(1 if rank else 0)

    n = len(ranks)
    hit = lambda t: sum(1 for r in ranks if r is not None and r <= t) / n if n else 0.0
    mrr = sum(1 / r for r in ranks if r) / n if n else 0.0
    print(f"样本={len(data)} QA={n} 用时={time.time() - t0:.1f}s embedder={emb.name} mode={args.mode} cat={args.only_cat or 'all'}")
    print(f"检索命中: @1={hit(1):.3f} @3={hit(3):.3f} @5={hit(5):.3f} @{args.k}={hit(args.k):.3f} MRR={mrr:.3f}")
    for cat, vals in sorted(per_cat.items()):
        print(f"  {CATS.get(cat, cat):<4} n={len(vals):<4} 命中={sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    main()
