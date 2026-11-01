"""脑区定向测试：映射、查询路由、检索加权、分区衰减。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from neuron_memory.memory import NeuronMemory, query_regions, region_of, REGION_DECAY, _now
from neuron_memory.embedder import get_embedder


def note(ntype: str, tier: str = "short") -> dict:
    return {"type": ntype, "tier": tier}


def main() -> None:
    ok = 0
    fail = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"PASS {name}")
        else:
            fail += 1
            print(f"FAIL {name} {extra}")

    check("preference -> emotion", region_of(note("preference")) == "emotion")
    check("decision -> executive", region_of(note("decision")) == "executive")
    check("project -> executive", region_of(note("project")) == "executive")
    check("concept -> semantic", region_of(note("concept")) == "semantic")
    check("fact -> hippocampus", region_of(note("fact")) == "hippocampus")
    check("long tier -> deep", region_of(note("fact", "long")) == "deep")

    check("cue emotion", query_regions("我喜欢什么口味") == {"emotion"})
    check("cue executive", query_regions("这个项目计划的进度安排") == {"executive"})
    check("cue semantic", query_regions("这个概念的定义和原理") == {"semantic"})
    check("cue deep", query_regions("以前最早发生过什么") == {"deep"})
    check("no cue", query_regions("今天天气不错") == set())

    emb = get_embedder("fastembed")
    tmp = Path(tempfile.mkdtemp(prefix="region_"))
    db = tmp / "r.db"
    mem = NeuronMemory(str(db), embedder=emb)

    # 同文本、不同类型：只有区域加权能决定顺序
    text = "咖啡"
    ids = {}
    for ntype, importance in (("fact", 0.6), ("preference", 0.6)):
        nid = mem.store.insert_note(text, ntype, importance)
        mem.store.set_embedding(nid, emb.embed(text))
        ids[ntype] = nid
    mem.store.conn.commit()

    rows = mem.recall("喜欢咖啡", 2)
    order = [r["type"] for r in rows]
    check("region boost ranks preference first", order and order[0] == "preference", str(order))

    plain = mem.recall("咖啡", 2)
    check("no-cue query has no boost", len(plain) == 2)

    # 分区衰减：同一时间/重要度，情感区应比海马体衰减慢
    now = _now()
    base = {"importance": 0.6, "n_eff": 0.0, "updated_at": "2026-01-01T00:00:00",
            "last_access": None, "type": "fact", "tier": "short"}
    fact = dict(base)
    pref = dict(base, type="preference")
    deep = dict(base, type="fact", tier="long")
    v_fact = mem._memory_value(fact, now)
    v_pref = mem._memory_value(pref, now)
    v_deep = mem._memory_value(deep, now)
    check("emotion decays slower", v_pref > v_fact)
    check("deep decays slower", v_deep > v_pref)
    check("region decay table", REGION_DECAY["emotion"] > 1 and REGION_DECAY["deep"] > REGION_DECAY["emotion"])

    print(f"RESULT {ok} passed, {fail} failed")
    raise SystemExit(1 if fail else 0)


if __name__ == "__main__":
    main()
