"""实体边参数快速对照（LoCoMo 子集 3 样本）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder

from .locomo_eval import turns_from
from .tune_recall import CONFIGS, build_sample, run_eval

VARIANTS = {
    "no_entity": None,
    "ent_w25_df08": dict(weight=0.25, max_per_entity=2, max_df_ratio=0.08),
    "ent_w15_df05": dict(weight=0.15, max_per_entity=1, max_df_ratio=0.05),
    "ent_w25_df05_m3": dict(weight=0.25, max_per_entity=3, max_df_ratio=0.05),
}


def main() -> None:
    data = json.loads(Path("data/locomo10.json").read_text("utf-8"))[:3]
    emb = get_embedder("fastembed")
    tmpdir = Path("data/tune_tmp")
    tmpdir.mkdir(exist_ok=True)
    built = []
    for si, sample in enumerate(data):
        mem, dia_map = build_sample(si, sample, emb, tmpdir)
        built.append((mem, dia_map, sample["qa"]))

    for name, params in VARIANTS.items():
        for mem, _, _ in built:
            mem.store.conn.execute("DELETE FROM links WHERE kind = 'entity'")
            mem.store.conn.execute("DELETE FROM note_entities")
        if params:
            for mem, _, _ in built:
                mem.build_entity_links(**params)
        t0 = time.time()
        agg = {"hit@10": [], "mrr": [], "multihop": []}
        for mem, dia_map, qas in built:
            r = run_eval(mem, dia_map, qas, CONFIGS["A_current"])
            agg["hit@10"].append(r["hit@10"])
            agg["mrr"].append(r["mrr"])
            agg["multihop"].append(r["multihop"])
        avg = {k: round(sum(v) / len(v), 3) for k, v in agg.items()}
        print(f"{name:<16} hit@10={avg['hit@10']:.3f} mrr={avg['mrr']:.3f} multihop={avg['multihop']:.3f} ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
