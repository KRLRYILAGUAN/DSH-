"""核心记忆体：SQLite 存储 + 向量检索 + 关联图 + 衰减/巩固。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from .embedder import get_embedder

SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT NOT NULL,
    type         TEXT NOT NULL DEFAULT 'fact',
    importance   REAL NOT NULL DEFAULT 0.6,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    last_access  TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    n_eff        REAL NOT NULL DEFAULT 0,
    tier         TEXT NOT NULL DEFAULT 'short',
    last_self    TEXT,
    superseded_by INTEGER,
    valid_from   TEXT,
    valid_to     TEXT,
    embedding    TEXT,
    archived     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS raw_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    text    TEXT,
    note_id INTEGER,
    meta    TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT,
    session_id TEXT,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    meta       TEXT
);
CREATE TABLE IF NOT EXISTS entities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL DEFAULT 'concept',
    aliases    TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS note_entities (
    note_id   INTEGER NOT NULL,
    entity    TEXT NOT NULL,
    entity_id INTEGER,
    PRIMARY KEY (note_id, entity)
);
CREATE TABLE IF NOT EXISTS links (
    src        INTEGER NOT NULL,
    dst        INTEGER NOT NULL,
    weight     REAL NOT NULL DEFAULT 0.5,
    kind       TEXT NOT NULL DEFAULT 'similar',
    created_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to   TEXT,
    PRIMARY KEY (src, dst)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_notes_archived ON notes (archived);
CREATE INDEX IF NOT EXISTS idx_notes_active ON notes (archived, superseded_by);
CREATE INDEX IF NOT EXISTS idx_links_dst ON links (dst);
CREATE INDEX IF NOT EXISTS idx_links_src ON links (src);
CREATE TABLE IF NOT EXISTS note_entities (
    note_id INTEGER NOT NULL,
    entity  TEXT NOT NULL,
    PRIMARY KEY (note_id, entity)
);
CREATE INDEX IF NOT EXISTS idx_entity ON note_entities (entity);
"""


def default_db_path() -> Path:
    """数据默认放在项目目录内：删掉整个文件夹 = 彻底清除。"""
    return Path(__file__).resolve().parents[1] / "data" / "neuron.db"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _days_since(then: datetime, now: datetime) -> float:
    return max(0.0, (now - then).total_seconds() / 86400.0)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def char_overlap(query: str, text: str) -> float:
    """中文查询的字级命中率，弥补哈希向量的粗糙。"""
    q = {ch for ch in query if "\u4e00" <= ch <= "\u9fff"}
    if not q:
        return 0.0
    t = {ch for ch in text if "\u4e00" <= ch <= "\u9fff"}
    return len(q & t) / len(q)


class Store:
    """SQLite 持久化。所有读写都走这里，方便以后换后端。"""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._vec_cache: dict[int, tuple[str, list[float]]] = {}
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(notes)")}
        for name, decl in (
            ("n_eff", "REAL NOT NULL DEFAULT 0"),
            ("tier", "TEXT NOT NULL DEFAULT 'short'"),
            ("last_self", "TEXT"),
            ("superseded_by", "INTEGER"),
            ("valid_from", "TEXT"),
            ("valid_to", "TEXT"),
            ("episode_id", "INTEGER"),
            ("pinned", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                self.conn.execute(f"ALTER TABLE notes ADD COLUMN {name} {decl}")
        self.conn.execute("UPDATE notes SET valid_from = created_at WHERE valid_from IS NULL")
        lcols = {r[1] for r in self.conn.execute("PRAGMA table_info(links)")}
        for name, decl in (("valid_from", "TEXT"), ("valid_to", "TEXT")):
            if name not in lcols:
                self.conn.execute(f"ALTER TABLE links ADD COLUMN {name} {decl}")
        self.conn.execute("UPDATE links SET valid_from = created_at WHERE valid_from IS NULL")
        necols = {r[1] for r in self.conn.execute("PRAGMA table_info(note_entities)")}
        if "entity_id" not in necols:
            self.conn.execute("ALTER TABLE note_entities ADD COLUMN entity_id INTEGER")
        self.conn.execute(
            "UPDATE notes SET valid_to = updated_at WHERE superseded_by IS NOT NULL AND valid_to IS NULL"
        )
        self.conn.executescript(INDEXES)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version' AND CAST(value AS INTEGER) < ?",
            (SCHEMA_VERSION, SCHEMA_VERSION),
        )
        self.conn.commit()

    def add_episode(self, text: str, source: str = "agent", session_id: str | None = None, meta: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO episodes (source, session_id, text, created_at, meta) VALUES (?, ?, ?, ?, ?)",
            (source, session_id, text, _iso(_now()), json.dumps(meta or {}, ensure_ascii=False)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_episode(self, eid: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM episodes WHERE id = ?", (eid,)).fetchone()
        return dict(row) if row else None

    # --- 笔记 ---
    def insert_note(self, text: str, ntype: str, importance: float, episode_id: int | None = None) -> int:
        now = _iso(_now())
        cur = self.conn.execute(
            "INSERT INTO notes (text, type, importance, created_at, updated_at, n_eff, valid_from, episode_id) "
            "VALUES (?, ?, ?, ?, ?, 1.0, ?, ?)",
            (text, ntype, importance, now, now, now, episode_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_note(self, nid: int, text: str, importance: float, vec: list[float]) -> None:
        self.conn.execute(
            "UPDATE notes SET text = ?, importance = ?, embedding = ?, updated_at = ? WHERE id = ?",
            (text, importance, json.dumps(vec), _iso(_now()), nid),
        )
        self.conn.commit()

    def set_embedding(self, nid: int, vec: list[float]) -> None:
        self.conn.execute(
            "UPDATE notes SET embedding = ?, updated_at = ? WHERE id = ?",
            (json.dumps(vec), _iso(_now()), nid),
        )
        self.conn.commit()

    def set_importance(self, nid: int, value: float) -> None:
        self.conn.execute("UPDATE notes SET importance = ? WHERE id = ?", (value, nid))
        self.conn.commit()

    def touch(self, ids: list[int]) -> None:
        if not ids:
            return
        now = _iso(_now())
        for nid in ids:
            self.conn.execute(
                "UPDATE notes SET access_count = access_count + 1, last_access = ? WHERE id = ?",
                (now, nid),
            )
        self.conn.commit()

    def archive(self, ids: list[int]) -> None:
        for nid in ids:
            self.conn.execute("UPDATE notes SET archived = 1, valid_to = ? WHERE id = ?", (_iso(_now()), nid))
            self.invalidate_links(nid)
        self.conn.commit()

    def unarchive(self, nid: int) -> None:
        self.conn.execute("UPDATE notes SET archived = 0 WHERE id = ?", (nid,))
        self.conn.commit()

    def delete(self, nid: int) -> None:
        self.conn.execute("DELETE FROM notes WHERE id = ?", (nid,))
        self.conn.execute("DELETE FROM links WHERE src = ? OR dst = ?", (nid, nid))
        self._vec_cache.pop(nid, None)
        self.conn.commit()

    def all_notes(self, include_archived: bool = False, include_superseded: bool = False) -> list[dict]:
        conds = []
        if not include_archived:
            conds.append("archived = 0")
        if not include_superseded:
            conds.append("superseded_by IS NULL")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = self.conn.execute(
            f"SELECT id, text, type, importance, created_at, updated_at, "
            f"last_access, access_count, n_eff, tier, last_self, superseded_by, "
            f"valid_from, valid_to, archived, embedding "
            f"FROM notes {where} ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            raw = d.pop("embedding")
            cached = self._vec_cache.get(r["id"])
            if cached and cached[0] == r["updated_at"]:
                d["vec"] = cached[1]
            else:
                vec = json.loads(raw or "[]")
                self._vec_cache[r["id"]] = (r["updated_at"], vec)
                d["vec"] = vec
            out.append(d)
        return out

    def get(self, nid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, text, type, importance, created_at, updated_at, last_access, "
            "access_count, n_eff, tier, last_self, superseded_by, valid_from, valid_to, "
            "archived, embedding, pinned, episode_id FROM notes WHERE id = ?",
            (nid,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["vec"] = json.loads(d.pop("embedding") or "[]")
        return d

    def backup(self, path: str | Path) -> Path:
        """Consistent online backup (SQLite backup API)."""
        dest = Path(path).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(dest))
        try:
            self.conn.backup(conn)
        finally:
            conn.close()
        return dest

    def close(self) -> None:
        self.conn.close()

    def set_episode(self, nid: int, eid: int) -> None:
        self.conn.execute("UPDATE notes SET episode_id = ? WHERE id = ?", (eid, nid))
        self.conn.commit()

    def set_n_eff(self, nid: int, value: float) -> None:
        self.conn.execute("UPDATE notes SET n_eff = ? WHERE id = ?", (value, nid))
        self.conn.commit()

    def set_tier(self, nid: int, tier: str) -> None:
        row = self.conn.execute("SELECT tier FROM notes WHERE id = ?", (nid,)).fetchone()
        old = row[0] if row else None
        self.conn.execute("UPDATE notes SET tier = ? WHERE id = ?", (tier, nid))
        if old is not None and old != tier:
            kind = "promote" if tier == "long" else "demote"
            self.record_raw(kind, None, nid, {"from": old, "to": tier})
        self.conn.commit()

    def set_last_self(self, nid: int) -> None:
        self.conn.execute("UPDATE notes SET last_self = ? WHERE id = ?", (_iso(_now()), nid))
        self.conn.commit()

    def set_pinned(self, nid: int, pinned: bool = True) -> None:
        self.conn.execute("UPDATE notes SET pinned = ? WHERE id = ?", (1 if pinned else 0, nid))
        self.conn.commit()

    def pinned_notes(self) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM notes WHERE pinned = 1 AND archived = 0 ORDER BY id"
            )
        ]

    def upsert_entity(self, name: str, etype: str = "concept", aliases: list[str] | None = None) -> int:
        name = name.strip()
        if not name:
            raise ValueError("实体名不能为空")
        row = self.conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row[0])
        cur = self.conn.execute(
            "INSERT INTO entities (name, type, aliases, created_at) VALUES (?, ?, ?, ?)",
            (name, etype, json.dumps(aliases or [], ensure_ascii=False), _iso(_now())),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def link_note_entity(self, nid: int, name: str, etype: str = "concept") -> int:
        eid = self.upsert_entity(name, etype)
        self.conn.execute(
            "INSERT OR IGNORE INTO note_entities (note_id, entity, entity_id) VALUES (?, ?, ?)",
            (nid, name.strip(), eid),
        )
        self.conn.commit()
        return eid

    def entities_for_note(self, nid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT e.name, e.type FROM note_entities ne "
            "LEFT JOIN entities e ON e.id = ne.entity_id WHERE ne.note_id = ?",
            (nid,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_entities(self, nid: int, ents: set[str]) -> None:
        for e in sorted(ents):
            self.link_note_entity(nid, e)

    def set_superseded(self, old_id: int, new_id: int) -> None:
        self.conn.execute(
            "UPDATE notes SET superseded_by = ?, valid_to = ? WHERE id = ?",
            (new_id, _iso(_now()), old_id),
        )
        self.invalidate_links(old_id)
        self.conn.commit()

    def clear_superseded(self, nid: int) -> None:
        self.conn.execute(
            "UPDATE notes SET superseded_by = NULL, valid_to = NULL WHERE id = ?", (nid,)
        )
        self.conn.commit()

    def record_raw(self, kind: str, text: str, note_id: int | None, meta: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO raw_events (ts, kind, text, note_id, meta) VALUES (?, ?, ?, ?, ?)",
            (_iso(_now()), kind, text, note_id, json.dumps(meta or {}, ensure_ascii=False)),
        )
        self.conn.commit()

    def raw_events(self, nid: int | None = None, limit: int = 20) -> list[dict]:
        if nid is None:
            rows = self.conn.execute(
                "SELECT id, ts, kind, text, note_id, meta FROM raw_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, ts, kind, text, note_id, meta FROM raw_events WHERE note_id = ? ORDER BY id DESC LIMIT ?",
                (nid, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- 关联 ---
    def add_link(self, a: int, b: int, weight: float, kind: str = "similar") -> None:
        src, dst = (a, b) if a < b else (b, a)
        now = _iso(_now())
        self.conn.execute(
            "INSERT INTO links (src, dst, weight, kind, created_at, valid_from) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(src, dst) DO UPDATE SET weight = MAX(weight, excluded.weight), valid_to = NULL",
            (src, dst, min(1.0, weight), kind, now, now),
        )
        self.conn.commit()

    def invalidate_links(self, nid: int) -> None:
        """Expire edges touching a note; keep the rows for history."""
        self.conn.execute(
            "UPDATE links SET valid_to = ? WHERE valid_to IS NULL AND (src = ? OR dst = ?)",
            (_iso(_now()), nid, nid),
        )
        self.conn.commit()

    def neighbors(self, nid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT dst AS other, weight FROM links WHERE src = ? AND valid_to IS NULL "
            "UNION ALL SELECT src AS other, weight FROM links WHERE dst = ? AND valid_to IS NULL",
            (nid, nid),
        ).fetchall()
        return [dict(r) for r in rows]

    def boost_link(self, a: int, b: int, eta: float = 0.02) -> None:
        src, dst = (a, b) if a < b else (b, a)
        self.conn.execute(
            "UPDATE links SET weight = MIN(1.0, weight + ?), valid_to = NULL WHERE src = ? AND dst = ?",
            (eta, src, dst),
        )
        self.conn.commit()

    def merge_into(self, keep: int, drop: int) -> None:
        keep_row = self.conn.execute("SELECT * FROM notes WHERE id = ?", (keep,)).fetchone()
        drop_row = self.conn.execute("SELECT * FROM notes WHERE id = ?", (drop,)).fetchone()
        if not keep_row or not drop_row:
            return
        text = keep_row["text"]
        if drop_row["text"] not in text:
            text = f"{text}；{drop_row['text']}"
        importance = max(keep_row["importance"], drop_row["importance"])
        access = keep_row["access_count"] + drop_row["access_count"]
        n_eff = keep_row["n_eff"] + drop_row["n_eff"]
        self.conn.execute(
            "UPDATE notes SET text = ?, importance = ?, access_count = ?, n_eff = ?, updated_at = ? WHERE id = ?",
            (text, importance, access, n_eff, _iso(_now()), keep),
        )
        for nb in self.neighbors(drop):
            if nb["other"] == keep:
                continue  # 防止自环
            self.add_link(keep, nb["other"], nb["weight"])
        self.conn.execute("DELETE FROM links WHERE src = ? OR dst = ?", (drop, drop))
        self.conn.execute("DELETE FROM notes WHERE id = ?", (drop,))
        self._vec_cache.pop(drop, None)
        self.conn.commit()

    def counts(self) -> dict:
        active = self.conn.execute("SELECT COUNT(*) FROM notes WHERE archived = 0 AND superseded_by IS NULL").fetchone()[0]
        archived = self.conn.execute("SELECT COUNT(*) FROM notes WHERE archived = 1").fetchone()[0]
        superseded = self.conn.execute("SELECT COUNT(*) FROM notes WHERE superseded_by IS NOT NULL").fetchone()[0]
        links = self.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        return {"active": active, "archived": archived, "superseded": superseded, "links": links}


REGION_DECAY = {
    "hippocampus": 1.0,
    "emotion": 1.25,
    "executive": 1.10,
    "semantic": 1.05,
    "deep": 1.50,
    "chatter": 0.25,
}

QUERY_CUES = {
    "emotion": ("喜欢", "偏好", "讨厌", "爱", "习惯", "口味", "情绪", "心情", "介意", "想要"),
    "executive": ("决定", "计划", "项目", "任务", "安排", "负责", "进度", "方案", "目标"),
    "semantic": ("概念", "定义", "原理", "方法", "技能", "怎么", "如何", "区别"),
    "deep": ("以前", "最早", "长期", "一直", "历史", "最初", "从前"),
}


def region_of(note: dict) -> str:
    """Same mapping as the viewer: type/tier → brain region."""
    if note.get("type") == "chat":
        return "chatter"
    if note.get("tier") == "long":
        return "deep"
    ntype = note.get("type")
    if ntype == "preference":
        return "emotion"
    if ntype in ("decision", "project"):
        return "executive"
    if ntype in ("concept", "skill"):
        return "semantic"
    return "hippocampus"


def query_regions(query: str) -> set[str]:
    """Cue-based routing: which regions a query is likely about."""
    hits = {region for region, cues in QUERY_CUES.items() if any(cue in query for cue in cues)}
    return hits


class NeuronMemory:
    """对外接口：remember / recall / forget / consolidate。"""

    merge_threshold = 0.95
    link_threshold = 0.15
    max_links = 5
    expand_seeds = 3
    hop_decay = 0.35
    promote_n = 3.0  # baseline n_eff starts at 1.0; user mention +1.0, self recall +0.4
    self_cooldown_min = 5.0
    conflict_threshold = 0.75
    region_boost = 0.03
    NEGATION_PREDICATES = (
        "喜欢", "爱", "要", "想", "是", "在", "去", "用", "吃", "喝",
        "买", "让", "接受", "同意", "支持", "讨厌", "习惯", "需要", "加", "放",
    )
    REWRITE_MARKERS = (
        "改成", "改为", "换成", "换为", "更正", "纠正", "不再",
        "搬到", "搬去", "改到", "换到", "调到", "转去", "变成", "更新为", "改用", "现在是",
    )
    WEEKDAYS = (
        "周一", "周二", "周三", "周四", "周五", "周六", "周日",
        "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期天",
    )

    def __init__(self, db_path: str | Path | None = None, embedder=None, reranker=None):
        self.store = Store(db_path or default_db_path())
        self.embedder = embedder or get_embedder()
        self.reranker = reranker
        name = getattr(self.embedder, "name", "")
        if "fastembed" in name:
            self.merge_threshold = 0.92
            self.link_threshold = 0.45
            self.weights = {
                "sim": 0.35, "bm25": 0.25, "ent": 0.08,
                "S": 0.10, "rec": 0.05, "lex": 0.12, "time": 0.05,
            }
            self.sim_floor, self.sim_span = 0.20, 0.60
            self.hop_decay = 0.25
        else:
            self.weights = {
                "sim": 0.30, "bm25": 0.30, "ent": 0.05,
                "S": 0.10, "rec": 0.05, "lex": 0.15, "time": 0.05,
            }
            self.sim_floor, self.sim_span = 0.0, 1.0
            self.hop_decay = 0.35
        self._token_cache: dict[str, list[str]] = {}

    # --- 记 ---
    @classmethod
    def _polarity(cls, text: str) -> set[tuple[str, bool]]:
        out: set[tuple[str, bool]] = set()
        for pred in cls.NEGATION_PREDICATES:
            idx = text.find(pred)
            while idx != -1:
                prefix = text[max(0, idx - 2) : idx]
                neg = any(ch in prefix for ch in "不没别勿未非")
                out.add((pred, neg))
                idx = text.find(pred, idx + 1)
        return out

    @classmethod
    def _conflict_signals(cls, old: str, new: str) -> list[str]:
        """规则冲突检测：否定极性、数字、星期、改写标记。返回命中的信号。"""
        signals: list[str] = []
        pa, pb = cls._polarity(old), cls._polarity(new)
        for pred in {p for p, _ in pa} & {p for p, _ in pb}:
            va = {neg for p, neg in pa if p == pred}
            vb = {neg for p, neg in pb if p == pred}
            if va != vb:
                signals.append(f"极性:{pred}")
        nums_a = set(re.findall(r"\d+", old))
        nums_b = set(re.findall(r"\d+", new))
        if nums_a and nums_b and nums_a != nums_b:
            signals.append("数字不同")
        wa = {w for w in cls.WEEKDAYS if w in old}
        wb = {w for w in cls.WEEKDAYS if w in new}
        if (wa or wb) and wa != wb:
            signals.append("星期不同")
        for marker in cls.REWRITE_MARKERS:
            if marker in new and marker not in old:
                signals.append(f"改写:{marker}")
                break
        return signals

    def remember(
        self,
        text: str,
        ntype: str = "fact",
        importance: float | None = None,
        episode: str | None = None,
        source: str = "agent",
        session_id: str | None = None,
        entities: list[str] | None = None,
    ) -> tuple[int, str]:
        text = " ".join(text.split())
        if not text:
            raise ValueError("记忆内容不能为空")
        episode_id = self.store.add_episode(episode, source, session_id) if episode else None
        ents = set(entities or []) | self.extract_entities(text)
        vec = self.embedder.embed(text)
        rows = self.store.all_notes()

        best = None
        for r in rows:
            sim = cosine(vec, r["vec"])
            if best is None or sim > best[1]:
                best = (r, sim)

        marked = any(marker in text for marker in self.REWRITE_MARKERS)
        conflict_floor = 0.4 if marked else self.conflict_threshold
        if best and best[1] >= conflict_floor:
            r, sim = best
            signals = self._conflict_signals(r["text"], text)
            if signals:
                nid = self.store.insert_note(
                    text, ntype, 0.6 if importance is None else max(0.0, min(1.0, importance)), episode_id
                )
                self.store.set_embedding(nid, vec)
                for ent in ents:
                    self.store.link_note_entity(nid, ent)
                self.store.set_superseded(r["id"], nid)
                self.store.record_raw(
                    "supersede", text, nid,
                    {"old": r["id"], "sim": round(sim, 3), "signals": signals},
                )
                return nid, f"superseded #{r['id']}"
            near_duplicate = r["text"] in text or text in r["text"] or sim >= 0.97
            if sim >= self.merge_threshold and near_duplicate:
                keep = text if len(text) > len(r["text"]) else r["text"]
                imp = max(r["importance"], importance if importance is not None else 0.0)
                self.store.update_note(r["id"], keep, imp, vec)
                for ent in ents:
                    self.store.link_note_entity(r["id"], ent)
                if episode_id and not r.get("episode_id"):
                    self.store.set_episode(r["id"], episode_id)
                self.store.set_n_eff(r["id"], r["n_eff"] + 1.0)
                self.store.record_raw("merge", text, r["id"], {"sim": round(sim, 3)})
                return r["id"], "merged"

        nid = self.store.insert_note(
            text, ntype, 0.6 if importance is None else max(0.0, min(1.0, importance)), episode_id
        )
        self.store.set_embedding(nid, vec)
        for ent in ents:
            self.store.link_note_entity(nid, ent)
        sims = sorted(
            ((r["id"], cosine(vec, r["vec"])) for r in rows),
            key=lambda x: x[1],
            reverse=True,
        )
        for dst, sim in [x for x in sims if x[1] >= self.link_threshold][: self.max_links]:
            self.store.add_link(nid, dst, sim)
        self.store.record_raw("remember", text, nid, {"episode_id": episode_id} if episode_id else None)
        return nid, "created"

    # --- 人格卡（置顶身份记忆，不衰减） ---
    def persona_add(self, text: str, importance: float = 1.0) -> tuple[int, str]:
        nid, mode = self.remember(text, "identity", max(0.9, importance))
        self.store.set_pinned(nid, True)
        self.store.set_tier(nid, "long")
        self.store.set_n_eff(nid, 5.0)
        self.store.record_raw("persona", text, nid)
        return nid, mode

    def persona_show(self) -> list[dict]:
        return self.store.pinned_notes()

    def persona_clear(self) -> list[int]:
        ids = [r["id"] for r in self.store.pinned_notes()]
        for nid in ids:
            self.store.set_pinned(nid, False)
        if ids:
            self.store.archive(ids)
        return ids

    # --- 闲聊流（低权重、快衰减、默认不参与检索） ---
    def remember_chat(self, text: str, episode: str | None = None) -> tuple[int, str]:
        return self.remember(text, "chat", 0.12, episode=episode, source="chat")

    # --- 忆 ---
    def recall(
        self,
        query: str,
        k: int = 5,
        as_of: str | None = None,
        rerank: bool = False,
        include_chat: bool = False,
    ) -> list[dict]:
        rows = self.store.all_notes(include_superseded=bool(as_of))
        if not include_chat:
            rows = [r for r in rows if r.get("type") != "chat"]
        if as_of:
            cutoff = _parse(as_of)
            if cutoff is not None:
                rows = [
                    r
                    for r in rows
                    if (not r["valid_from"] or (_parse(r["valid_from"]) or cutoff) <= cutoff)
                    and (not r["valid_to"] or (_parse(r["valid_to"]) or cutoff) > cutoff)
                ]
        if not rows:
            return []
        qvec = self.embedder.embed_query(query)
        now = _now()
        qregions = query_regions(query)
        sims = self._similarities(qvec, rows)
        bm25 = self._bm25(query, rows)
        qents = self.extract_entities(query)
        ent_by_note: dict[int, set[str]] = {}
        if qents:
            marks = ",".join("?" * len(qents))
            for erow in self.store.conn.execute(
                f"SELECT note_id, entity FROM note_entities WHERE entity IN ({marks})", tuple(qents)
            ):
                ent_by_note.setdefault(erow[0], set()).add(erow[1])

        candidates: list[tuple[dict, float, float, float, float, float]] = []
        for r, sim, bm in zip(rows, sims, bm25):
            ent_hit = self._entity_score(qents, r["text"], ent_by_note.get(r["id"]))
            if sim < 0.05 and bm == 0.0 and ent_hit == 0.0:
                continue
            idle = _days_since(_parse(r["last_access"] or r["created_at"]) or now, now)
            recency = math.exp(-idle / 30.0)
            lex = char_overlap(query, r["text"])
            sval = self._memory_value(r, now)
            candidates.append((r, sim, bm, recency, lex, sval))
        max_s = max((c[5] for c in candidates), default=0.0) or 1.0

        by_id = {r["id"]: r for r in rows}
        s_by_id: dict[int, float] = {}
        totals: dict[int, float] = {}
        for r, sim, bm, recency, lex, sval in candidates:
            sim_n = min(1.0, max(0.0, (sim - self.sim_floor) / self.sim_span))
            ent = self._entity_score(qents, r["text"], ent_by_note.get(r["id"]))
            tb = self._time_boost(query, r)
            s_by_id[r["id"]] = sval
            totals[r["id"]] = (
                self.weights["sim"] * sim_n
                + self.weights["bm25"] * bm
                + self.weights["ent"] * ent
                + self.weights["S"] * (sval / max_s)
                + self.weights["rec"] * recency
                + self.weights["lex"] * lex
                + self.weights["time"] * tb
                + self.region_boost * (1.0 if region_of(r) in qregions else 0.0)
            )

        # 扩散激活：从 top-3 种子沿关联边扩一跳
        seeds = sorted(totals.items(), key=lambda x: x[1], reverse=True)[: self.expand_seeds]
        for seed_id, seed_score in seeds:
            for nb in self.store.neighbors(seed_id):
                if nb["other"] not in by_id:
                    continue
                bonus = seed_score * nb["weight"] * self.hop_decay
                totals[nb["other"]] = totals.get(nb["other"], 0.0) + bonus

        fetch_k = max(k * 3, 30) if (rerank and self.reranker is not None) else k
        ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:fetch_k]
        if rerank and self.reranker is not None and len(ranked) > k:
            texts = [by_id[i]["text"] for i, _ in ranked]
            scores = list(self.reranker.rerank(query, texts))
            order = sorted(range(len(ranked)), key=lambda idx: scores[idx], reverse=True)[:k]
            ranked = [ranked[idx] for idx in order]
        ids = [i for i, _ in ranked]
        self.store.touch(ids)
        # 召回即自检索：真实用到才算，权重 0.4；达到阈值晋升长期层
        for i in ids:
            r = by_id[i]
            neff = r.get("n_eff", 0.0) + 0.4
            self.store.set_n_eff(i, neff)
            r["n_eff"] = neff
            if neff >= self.promote_n or r["importance"] >= 0.8:
                if r.get("tier") != "long":
                    self.store.set_tier(i, "long")
        # Hebbian：同批被唤醒的节点互连加强
        for a, b in combinations(ids, 2):
            self.store.boost_link(a, b)
        return [
            {
                "id": i,
                "score": round(s, 4),
                "text": by_id[i]["text"],
                "type": by_id[i]["type"],
                "importance": by_id[i]["importance"],
                "n_eff": round(by_id[i].get("n_eff", 0.0), 2),
                "tier": by_id[i].get("tier", "short"),
                "S": round(s_by_id.get(i, 0.0), 4),
            }
            for i, s in ranked
        ]

    def _memory_value(self, r: dict, now) -> float:
        """双因子记忆值：重要度 × 复述增益 × 时间衰减（长期层衰减更慢）。"""
        if r.get("pinned"):
            return 1.0
        n = r.get("n_eff", 0.0)
        updated = _parse(r["updated_at"]) or now
        accessed = _parse(r["last_access"])
        last = max(updated, accessed) if accessed else updated
        idle = _days_since(last, now)
        half = 365.0 if r.get("tier") == "long" else 90.0
        tau = half * (1 + 0.5 * n) * REGION_DECAY.get(region_of(r), 1.0)
        return r["importance"] * (1 + 0.5 * math.log1p(n)) * math.exp(-idle / tau)

    def _tokens(self, text: str) -> list[str]:
        cached = self._token_cache.get(text)
        if cached is not None:
            return cached
        words = re.findall(r"[a-z0-9]+", text.lower())
        cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
        grams = [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
        toks = words + grams
        if len(self._token_cache) > 20000:
            self._token_cache.clear()
        self._token_cache[text] = toks
        return toks

    def _bm25(self, query: str, rows: list[dict]) -> list[float]:
        q = set(self._tokens(query))
        if not q or not rows:
            return [0.0] * len(rows)
        docs = [self._tokens(r["text"]) for r in rows]
        n = len(docs)
        avgdl = sum(len(d) for d in docs) / n or 1.0
        df = {t: sum(1 for d in docs if t in d) for t in q}
        k1, b = 1.5, 0.75
        scores = []
        for d in docs:
            s = 0.0
            L = len(d)
            for t in q:
                tf = d.count(t)
                if tf:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * L / avgdl))
            scores.append(s)
        mx = max(scores) or 1.0
        return [s / mx for s in scores]

    ENT_RE = re.compile(r"\b[A-Z][a-z]{1,}\b")

    def _entity_score(self, qents: set[str], text: str, note_ents: set[str] | None = None) -> float:
        if not qents:
            return 0.0
        have = note_ents or set()
        return sum(1 for e in qents if e in have or e in text) / len(qents)

    def extract_entities(self, text: str) -> set[str]:
        out = set(self.ENT_RE.findall(text))
        out |= set(re.findall(r"[「“\"《]([^」”\"》]{2,24})[」”\"》]", text))
        out |= set(re.findall(r"@([A-Za-z0-9_\-]{2,24})", text))
        return {e.strip() for e in out if 2 <= len(e.strip()) <= 24}

    def build_entity_links(
        self, weight: float = 0.25, max_per_entity: int = 2, max_df_ratio: float = 0.08
    ) -> int:
        """按实体共现补边：同一实体出现在多条记忆里就串起来，给多跳检索搭桥。

        常见实体（出现在超过 max_df_ratio 的记忆里）区分度低，不建边，避免毛球。
        """
        notes = self.store.all_notes()
        for r in notes:
            ents = self.extract_entities(r["text"])
            if ents:
                self.store.add_entities(r["id"], ents)
        rows = self.store.conn.execute(
            "SELECT entity, note_id FROM note_entities ORDER BY entity, note_id"
        ).fetchall()
        groups: dict[str, list[int]] = {}
        for entity, nid in rows:
            groups.setdefault(entity, []).append(nid)
        limit = max(3, int(len(notes) * max_df_ratio))
        added = 0
        for ids in groups.values():
            if len(ids) > limit:
                continue
            for i, a in enumerate(ids):
                for b in ids[i + 1 : i + 1 + max_per_entity]:
                    self.store.add_link(a, b, weight, kind="entity")
                    added += 1
        return added

    def _time_boost(self, query: str, r: dict) -> float:
        years = set(re.findall(r"\b((?:19|20)\d{2})\b", query))
        if not years or not r.get("valid_from"):
            return 0.0
        vf = _parse(r["valid_from"])
        return 1.0 if vf and str(vf.year) in years else 0.0

    def _similarities(self, qvec: list[float], rows: list[dict]) -> list[float]:
        if not rows:
            return []
        try:
            import numpy as np
        except Exception:
            return [cosine(qvec, r["vec"]) for r in rows]
        dims = {len(r["vec"]) for r in rows}
        if len(dims) != 1:
            return [cosine(qvec, r["vec"]) for r in rows]
        mat = np.asarray([r["vec"] for r in rows], dtype=np.float32)
        q = np.asarray(qvec, dtype=np.float32)
        qn = q / (np.linalg.norm(q) + 1e-9)
        norms = np.linalg.norm(mat, axis=1) + 1e-9
        return (mat @ qn / norms).tolist()

    # --- 忘 ---
    def mention(self, nid: int, source: str = "user") -> tuple[bool, str]:
        """显式提及一条记忆。source: user / self / consolidate / implicit。"""
        weights = {"user": 1.0, "self": 0.4, "consolidate": 0.3, "implicit": 0.1}
        weight = weights.get(source, 0.0)
        r = self.store.get(nid)
        if not r or r["archived"]:
            return False, "没有这条记忆"
        if r.get("superseded_by") is not None:
            return False, "该记忆已被新记忆取代"
        if source == "self":
            last = _parse(r["last_self"])
            if last and (_now() - last).total_seconds() < self.self_cooldown_min * 60:
                return False, "自检索冷却中"
            self.store.set_last_self(nid)
        neff = r["n_eff"] + weight
        self.store.set_n_eff(nid, neff)
        if neff >= self.promote_n or r["importance"] >= 0.8:
            self.store.set_tier(nid, "long")
        return True, f"#{nid} 有效复述 {neff:.2f}（{source}，+{weight:g}）"

    def rehearse(self, limit: int = 20) -> int:
        """巩固复习：挑重要记忆做一次低权重复述（+0.5），模拟夜间重放。"""
        rows = sorted(self.store.all_notes(), key=lambda r: -r["importance"])
        for r in rows[:limit]:
            neff = r["n_eff"] + 0.5
            self.store.set_n_eff(r["id"], neff)
            if neff >= self.promote_n or r["importance"] >= 0.8:
                self.store.set_tier(r["id"], "long")
        return min(limit, len(rows))

    def decay(self, half_life_days: float = 90.0) -> None:
        now = _now()
        for r in self.store.all_notes():
            updated = _parse(r["updated_at"]) or now
            accessed = _parse(r["last_access"])
            last_activity = max(updated, accessed) if accessed else updated  # 检索也算活动
            idle = _days_since(last_activity, now)
            hl = 365.0 if r.get("tier") == "long" else half_life_days
            factor = 0.5 ** (idle / hl)
            new_imp = max(0.02, r["importance"] * factor)
            if r.get("tier") == "long":
                new_imp = max(new_imp, 0.1)  # 长期层保底，不跌破
            if abs(new_imp - r["importance"]) > 1e-4:
                self.store.set_importance(r["id"], round(new_imp, 4))

    def forget(
        self,
        stale: bool = True,
        dry_run: bool = False,
        threshold: float = 0.15,
        idle_days: float = 60.0,
    ) -> list[dict]:
        if stale:
            self.decay()
        now = _now()
        candidates = []
        for r in self.store.all_notes():
            if r.get("pinned"):
                continue
            idle = _days_since(_parse(r["last_access"] or r["created_at"]) or now, now)
            if r["importance"] < threshold and idle >= idle_days:
                if r.get("tier") == "long" and idle < 365:
                    continue
                candidates.append(r)
        if not dry_run:
            self.store.archive([r["id"] for r in candidates])
        return candidates

    def forget_one(self, nid: int) -> None:
        self.store.delete(nid)

    def restore(self, nid: int) -> bool:
        """把已归档/被取代的记忆恢复回活跃集。"""
        r = self.store.get(nid)
        if not r:
            return False
        self.store.unarchive(nid)
        if r.get("superseded_by") is not None:
            self.store.clear_superseded(nid)
        return True

    # --- 巩固 ---
    def consolidate(self, threshold: float = 0.90) -> int:
        rows = self.store.all_notes()
        used: set[int] = set()
        merged = 0
        for i, r in enumerate(rows):
            if r["id"] in used:
                continue
            for r2 in rows[i + 1 :]:
                if r2["id"] in used:
                    continue
                if cosine(r["vec"], r2["vec"]) >= threshold:
                    self.store.merge_into(r["id"], r2["id"])
                    merged_text = self.store.get(r["id"])["text"]
                    self.store.set_embedding(r["id"], self.embedder.embed(merged_text))
                    used.add(r2["id"])
                    merged += 1
        return merged

    # --- 观察 ---
    def stats(self) -> dict:
        c = self.store.counts()
        rows = self.store.all_notes()
        avg = sum(r["importance"] for r in rows) / len(rows) if rows else 0.0
        tiers = {"short": 0, "long": 0}
        for r in rows:
            tiers[r.get("tier", "short")] = tiers.get(r.get("tier", "short"), 0) + 1
        return {
            **c,
            "avg_importance": round(avg, 3),
            "tiers": tiers,
            "embedder": self.embedder.name,
            "db": str(self.store.path),
        }
