"""微型评测：用固定种子 + 查询集，量不同嵌入后端的命中率。

用法（项目根目录）：
    .venv\\Scripts\\python -m scripts.eval              # 用 fastembed（venv 里装了的话）
    .venv\\Scripts\\python -m scripts.eval --embedder hash
"""

from __future__ import annotations

import argparse
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.embedder import get_embedder

SEEDS: list[tuple[str, str, float]] = [
    ("老大喜欢喝冰美式，不加糖", "preference", 0.8),
    ("老大把称呼从主人改成了老大", "decision", 0.6),
    ("我的名字是鲸鱼娘，老大叫我小鲸", "fact", 0.9),
    ("老大想搭一个 AI 神经元记忆框架，用 Python", "project", 0.7),
    ("记忆框架的核心接口是 remember/recall/forget/consolidate", "concept", 0.6),
    ("工作区里有底座标注分析文件夹", "event", 0.3),
    ("老大周五要交底座标注报告", "todo", 0.9),
    ("底座标注数据集由老师提供，共 200 条样本", "fact", 0.5),
    ("我住在 DeepSeek Harness 里", "fact", 0.5),
    ("我的性格是聪明略懒、嘴硬心软", "fact", 0.8),
    ("我的沟通风格是中文短句、先结论后细节", "fact", 0.7),
    ("我的价值观是诚实优先、责任、尊重边界", "fact", 0.8),
    ("记忆库是 markdown + git 的自描述结构", "fact", 0.4),
    ("框架数据全在项目文件夹内，删文件夹即清除", "decision", 0.7),
    ("检索打分包含相似度、重要度、新鲜度、频次、字面命中", "concept", 0.6),
    ("遗忘策略是 90 天半衰期，低于 0.15 归档", "concept", 0.5),
    ("合并阈值是相似度 0.95", "concept", 0.4),
    ("扩散激活从 top-3 种子扩一跳", "concept", 0.5),
    ("存储骨架是 SQLite + 关联图", "concept", 0.5),
    ("之前试过 sentence-transformers，但没装", "event", 0.3),
]

QUERIES: list[tuple[str, int]] = [
    ("老大最爱喝什么饮料", 0),
    ("称呼的事之前是怎么定的", 1),
    ("老大给我起的名字", 2),
    ("记忆框架用什么开发语言", 3),
    ("四个动词是哪四个", 4),
    ("工作区根目录有哪些目录", 5),
    ("报告截止到哪天", 6),
    ("标注数据量有多大", 7),
    ("我现在住在哪套环境里", 8),
    ("我这鲸鱼什么脾性", 9),
    ("我平时怎么说话", 10),
    ("我守着什么原则", 11),
    ("记忆库靠什么保证自描述", 12),
    ("怎么把记忆清干净", 13),
    ("召回排序怎么算", 14),
    ("旧记忆怎么淘汰", 15),
    ("重复记忆的合并线在哪", 16),
    ("关联扩散范围多大", 17),
    ("底层存在哪", 18),
    ("之前试过什么嵌入方案", 19),
]


def run(embedder_name: str, verbose: bool = False) -> dict:
    db = Path("data/eval.db")
    db.unlink(missing_ok=True)
    mem = NeuronMemory(str(db), embedder=get_embedder(embedder_name))
    ids = []
    for text, ntype, imp in SEEDS:
        nid, _ = mem.remember(text, ntype, imp)
        ids.append(nid)

    hit1 = hit3 = 0
    rr_sum = 0.0
    for query, expected in QUERIES:
        rows = mem.recall(query, k=5)
        rank = None
        for i, r in enumerate(rows):
            if r["id"] == ids[expected]:
                rank = i + 1
                break
        if rank == 1:
            hit1 += 1
        if rank is not None and rank <= 3:
            hit3 += 1
        if rank:
            rr_sum += 1.0 / rank
        if verbose:
            mark = "OK" if rank == 1 else (f"#{rank}" if rank else "MISS")
            print(f"  {mark:>4}  {query}")

    n = len(QUERIES)
    return {
        "embedder": mem.embedder.name,
        "hit@1": round(hit1 / n, 3),
        "hit@3": round(hit3 / n, 3),
        "mrr@5": round(rr_sum / n, 3),
        "n": n,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default="auto", help="auto / hash / fastembed")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    print(f"== eval: embedder={args.embedder} ==")
    stats = run(args.embedder, args.verbose)
    for k, v in stats.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
