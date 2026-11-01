"""核心自测：remember/recall/冲突/衰减/恢复/桥接/迁移/缓存一致性。"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path

from neuron_memory import NeuronMemory
from neuron_memory.bridge import import_memory
from neuron_memory.memory import _iso, _now, cosine

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, "" if cond else detail)


def main() -> None:
    tmp = Path("data") / f"selftest_{os.getpid()}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        m = NeuronMemory(str(tmp / "a.db"))
        nid, mode = m.remember("老大喜欢冰美式")
        check("remember created", mode == "created")
        rows = m.recall("老大喝什么", 3)
        check("recall hit", bool(rows) and rows[0]["id"] == nid)
        check("recall has S", "S" in rows[0])

        nid2, mode2 = m.remember("老大喜欢冰美式")
        check("dedupe merge", nid2 == nid and mode2 == "merged")

        nid3, mode3 = m.remember("老大不喜欢冰美式")
        check("conflict supersede", mode3.startswith("superseded"))
        check("old superseded", m.store.get(nid)["superseded_by"] == nid3)
        check("recall excludes superseded", nid not in [r["id"] for r in m.recall("冰美式", 5)])

        check("restore superseded", m.restore(nid))

        ok1, _ = m.mention(nid3, "self")
        ok2, _ = m.mention(nid3, "self")
        check("self cooldown", ok1 and not ok2)
        ok3, _ = m.mention(nid3, "user")
        check("user always allowed", ok3)

        m2 = NeuronMemory(str(tmp / "b.db"))
        x, _ = m2.remember("推广测试")
        for _ in range(3):
            m2.mention(x, "user")
        check("tier promotion", m2.store.get(x)["tier"] == "long")

        z, _ = m2.remember("来源测试", "fact", 0.5, episode="用户原话：测试来源")
        eid = m2.store.conn.execute("SELECT episode_id FROM notes WHERE id = ?", (z,)).fetchone()[0]
        ep = m2.store.get_episode(eid) if eid else None
        check("episode linked", ep is not None and ep["text"] == "用户原话：测试来源")

        m4 = NeuronMemory(str(tmp / "d.db"))
        u, _ = m4.remember("边测试一")
        v, _ = m4.remember("边测试二")
        m4.store.add_link(u, v, 0.5)
        m4.store.set_superseded(u, v)
        row = m4.store.conn.execute(
            "SELECT valid_to FROM links WHERE src = ? AND dst = ?", (min(u, v), max(u, v))
        ).fetchone()
        check("edge invalidated", row is not None and row["valid_to"] is not None)
        check("neighbors skip expired", m4.store.neighbors(u) == [])

        m5 = NeuronMemory(str(tmp / "e.db"))
        q, _ = m5.remember("「项目X」由 Alice 负责", "project", 0.7, entities=["Alice"])
        names = {e["name"] for e in m5.store.entities_for_note(q)}
        check("entities linked", {"Alice", "项目X"} <= names)

        m6 = NeuronMemory(str(tmp / "ent.db"))
        a1, _ = m6.remember("项目 Alpha 的负责人已定", "project", 0.6, entities=["Alice"])
        b1, _ = m6.remember("项目 Beta 的负责人已定", "project", 0.6, entities=["Bob"])
        top = m6.recall("Alice", 2)
        check("entity match ranks first", top and top[0]["id"] == a1)

        m7 = NeuronMemory(str(tmp / "g.db"))
        check("empty recall", m7.recall("x") == [])

        m8 = NeuronMemory(str(tmp / "p.db"))
        pid, _ = m8.persona_add("人格测试：短句、先结论")
        check("persona pinned", m8.persona_show() and m8.persona_show()[0]["id"] == pid)
        check("persona no decay", m8._memory_value(m8.store.get(pid), _now()) == 1.0)
        m8.persona_clear()
        check("persona cleared", m8.persona_show() == [])

        m9 = NeuronMemory(str(tmp / "chat.db"))
        m9.remember("周末去爬山", "event", 0.7)
        chat_id, _ = m9.remember_chat("聊了会儿周末爬山，气氛轻松")
        check("chat hidden by default", all(r["type"] != "chat" for r in m9.recall("周末", 5)))
        check("chat opt-in", any(r["id"] == chat_id for r in m9.recall("周末", 5, include_chat=True)))

        m3 = NeuronMemory(str(tmp / "c.db"))
        y, _ = m3.remember("衰减测试", "fact", 0.8)
        old = _iso(_now() - timedelta(days=400))
        nows = _iso(_now())
        conn = sqlite3.connect(str(tmp / "c.db"))
        conn.execute("UPDATE notes SET updated_at=?, last_access=? WHERE id=?", (old, nows, y))
        conn.commit()
        conn.close()
        m3.decay()
        check("decay keeps recent", abs(m3.store.get(y)["importance"] - 0.8) < 0.01)

        conn = sqlite3.connect(str(tmp / "c.db"))
        conn.execute("UPDATE notes SET last_access=? WHERE id=?", (old, y))
        conn.commit()
        conn.close()
        m3.decay()
        check("decay drops old", m3.store.get(y)["importance"] < 0.5)

        m4 = NeuronMemory(str(tmp / "d.db"))
        p, _ = m4.remember("框架用 SQLite 存储数据")
        m4.remember("框架用 SQLite 保存记录")
        m4.consolidate(threshold=0.5)
        merged = m4.store.get(p)
        check(
            "merge embedding fresh",
            cosine(merged["vec"], m4.embedder.embed(merged["text"])) > 0.99,
        )

        mem_dir = tmp / "mem"
        (mem_dir / "user").mkdir(parents=True)
        (mem_dir / "user" / "profile.md").write_text(
            "---\ntitle: x\n---\n\n- 老大是用户\n- 老大喜欢米饭\n", encoding="utf-8"
        )
        m5 = NeuronMemory(str(tmp / "e.db"))
        s1 = import_memory(m5, mem_dir)
        s2 = import_memory(m5, mem_dir)
        check("bridge idempotent", s1["imported"] == 2 and s2["imported"] == 0)

        try:
            m5.remember("   ")
            check("empty text raises", False)
        except ValueError:
            check("empty text raises", True)

        m6 = NeuronMemory(str(tmp / "f.db"))
        check("empty recall", m6.recall("x") == [])

        ids1 = [r["id"] for r in m4.recall("SQLite 存储", 5)]
        m4.store._vec_cache.clear()
        ids2 = [r["id"] for r in m4.recall("SQLite 存储", 5)]
        check("cache consistent", ids1 == ids2)

        old_db = tmp / "old.db"
        conn = sqlite3.connect(str(old_db))
        conn.executescript(
            """CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'fact', importance REAL NOT NULL DEFAULT 0.6,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_access TEXT,
            access_count INTEGER NOT NULL DEFAULT 0, embedding TEXT,
            archived INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE links (src INTEGER NOT NULL, dst INTEGER NOT NULL,
            weight REAL NOT NULL DEFAULT 0.5, kind TEXT NOT NULL DEFAULT 'similar',
            created_at TEXT NOT NULL, PRIMARY KEY (src, dst));"""
        )
        conn.execute(
            "INSERT INTO notes (text, type, importance, created_at, updated_at) "
            "VALUES ('旧库记忆','fact',0.5,'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        conn.close()
        m7 = NeuronMemory(str(old_db))
        row = m7.store.get(1)
        check("schema migration", row is not None and "n_eff" in row and row["tier"] == "short")

        m8 = NeuronMemory(str(tmp / "g.db"))
        ta, _ = m8.remember("老大喜欢冰美式")
        tb, _ = m8.remember("老大不喜欢冰美式")
        conn = sqlite3.connect(str(tmp / "g.db"))
        conn.execute(
            "UPDATE notes SET valid_from='2026-01-01T00:00:00+00:00', valid_to='2026-06-01T00:00:00+00:00' WHERE id=?",
            (ta,),
        )
        conn.execute(
            "UPDATE notes SET valid_from='2026-06-01T00:00:00+00:00', valid_to=NULL WHERE id=?",
            (tb,),
        )
        conn.commit()
        conn.close()
        now_ids = [r["id"] for r in m8.recall("冰美式", 5)]
        past_ids = [r["id"] for r in m8.recall("冰美式", 5, as_of="2026-03-01T00:00:00+00:00")]
        check("temporal current excludes old", now_ids == [tb])
        check("temporal as_of includes superseded", ta in past_ids and tb not in past_ids)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} passed")
    raise SystemExit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
