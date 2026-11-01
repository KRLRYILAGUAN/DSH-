"""记忆周期实验引擎：双因子记忆值 + 提及加深 + 静默期 + 遗忘检查。

阶段：
  interaction [0, 10min)   互动期，提及/检索计数，n 超过阈值 → 加深
  silent      [10, 15min)  静默期，不检索、不提及
  done        15min 之后   遗忘检查：n>2 保留并缩短，n<=2 遗忘
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

CFG_DEFAULT = {
    "cycle_min": 10.0,
    "silent_min": 5.0,
    "observe_min": 30.0,
    "threshold": 2,
    "theta": 0.15,
    "beta": 0.5,
    "tau0": 20.0,
    "tau_long_min": 10080.0,   # 长期层半衰期：7 天
    "promote_n": 3.0,          # 有效复述达到这个数 → 晋升长期层
    "rehearse": False,         # 是否在第一次检查后做一次「巩固复习」
    "rehearse_boost": 0.5,     # 每次复习折合几次复述
    "self_weight": 0.4,        # 自检索（回答中真的用到）的权重
    "consolidate_weight": 0.3, # 巩固复习的权重
    "self_cooldown_min": 5.0,  # 同一条记忆自检索的冷却（实验分钟）
    "gamma": 0.5,
    "speed": 1.0,
}

SEEDS: list[tuple[str, str, float]] = [
    ("记忆框架在 AI神经元记忆框架 文件夹里", "core", 0.7),
    ("老大让我叫老大，不再叫主人", "core", 0.7),
    ("检索打分 = 相似度 + 重要度 + 新鲜度 + 频次 + 字面命中", "core", 0.7),
    ("遗忘策略是 90 天半衰期，低于 0.15 归档", "core", 0.7),
    ("真向量模型用的是 bge-small-zh-v1.5", "core", 0.7),
    ("临时阈值：提及超过 2 次就加深", "detail", 0.45),
    ("静默期 5 分钟，期间不检索加深的记忆", "detail", 0.45),
    ("遗忘检查在实验开始后 15 分钟", "detail", 0.45),
    ("缩短只换显示和短版，raw 全文保留", "detail", 0.45),
    ("本轮参数 beta=0.5、tau0=20 分钟、gamma=0.5", "detail", 0.45),
    ("底座标注报告周五要交", "detail", 0.45),
    ("测试种子一共 12 条", "detail", 0.45),
]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _shorten(text: str, limit: int = 16) -> str:
    for sep in "，。！？；,;!?":
        idx = text.find(sep)
        if 0 < idx <= limit:
            return text[: idx + 1]
    return text[:limit] + ("…" if len(text) > limit else "")


def _chars(text: str) -> set[str]:
    return {c for c in text if not c.isspace()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _bigram_vec(text: str) -> dict[str, float]:
    t = "".join(ch for ch in text.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
    grams = {t[i : i + 2] for i in range(len(t) - 1)}
    grams |= {ch for ch in t if "\u4e00" <= ch <= "\u9fff"}
    return {g: 1.0 for g in grams}


def _cos_dict(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(w * b.get(k, 0.0) for k, w in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def cluster_texts(texts: list[str], k: int = 4) -> tuple[list[int], list[str]]:
    """字符 bigram + TF-IDF + k-means 分簇；标签取簇内「独占度」最高的词。"""
    n = len(texts)
    if n == 0:
        return [], []
    k = min(k, n)
    raw = [_bigram_vec(t) for t in texts]
    df: dict[str, int] = {}
    for v in raw:
        for g in v:
            df[g] = df.get(g, 0) + 1
    vecs = [
        {g: w * math.log((n + 1) / (df[g] + 1)) for g, w in v.items()}
        for v in raw
    ]
    cents = [vecs[0]]
    while len(cents) < k:
        best = max(range(n), key=lambda i: min(1 - _cos_dict(vecs[i], c) for c in cents))
        if vecs[best] in cents:
            break
        cents.append(vecs[best])
    assign = [0] * n
    for _ in range(30):
        new = [max(range(len(cents)), key=lambda c: _cos_dict(vecs[i], cents[c])) for i in range(n)]
        if new == assign:
            break
        assign = new
        for c in range(len(cents)):
            members = [i for i in range(n) if assign[i] == c]
            if not members:
                continue
            agg: dict[str, float] = {}
            for i in members:
                for g, w in vecs[i].items():
                    agg[g] = agg.get(g, 0.0) + w
            cents[c] = agg
    order = sorted(range(len(cents)), key=lambda c: -sum(1 for a in assign if a == c))
    remap = {old: new for new, old in enumerate(order)}
    assign = [remap[a] for a in assign]
    labels: list[str] = []
    for c in range(len(order)):
        counter: dict[str, int] = {}
        for i, a in enumerate(assign):
            if a != c:
                continue
            t = "".join(ch for ch in texts[i] if "\u4e00" <= ch <= "\u9fff")
            for g in {t[j : j + 3] for j in range(len(t) - 2)}:
                counter[g] = counter.get(g, 0) + 1
        scored = {
            g: cnt * math.log(1 + cnt) / math.log(1 + df.get(g, cnt))
            for g, cnt in counter.items()
        }
        label = min(scored.items(), key=lambda kv: (-kv[1], kv[0]))[0] if scored else f"簇{c + 1}"
        labels.append(label)
    return assign, labels


class Experiment:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict | None = None
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text("utf-8"))
            except Exception:
                self.data = None

    # --- 生命周期 ---
    def reset(self) -> None:
        self.data = None
        self.path.unlink(missing_ok=True)

    def start(self, speed: float = 1.0, demo: bool = False) -> None:
        self.data = {
            "started": True,
            "t0_ts": time.time(),
            "phase": "interaction",
            "config": {**CFG_DEFAULT, "speed": max(0.1, speed)},
            "memories": [
                {
                    "id": i + 1,
                    "text": text,
                    "kind": kind,
                    "B": base,
                    "n": 0,
                    "n_eff": 0.0,
                    "tier": "short",
                    "state": "active",
                    "short": None,
                    "last_mention": None,
                }
                for i, (text, kind, base) in enumerate(SEEDS)
            ],
            "log": [{"t": _now(), "msg": f"实验开始：{len(SEEDS)} 条种子，速度 ×{speed:g}"}],
            "history": [],
            "last_sample": 0.0,
        }
        assign, labels = cluster_texts([m["text"] for m in self.data["memories"]])
        for m, c in zip(self.data["memories"], assign):
            m["cluster"] = c
        self.data["clusters"] = [{"id": i, "label": lab} for i, lab in enumerate(labels)]
        self._save()
        if demo:
            for mid, times in {1: 3, 3: 3, 7: 3, 5: 2, 9: 1, 11: 2}.items():
                for _ in range(times):
                    self.mention(mid)
            self._log("演示模式：已自动提及部分记忆")

    def _elapsed_min(self) -> float:
        return (time.time() - float(self.data["t0_ts"])) / 60.0 * float(self.data["config"]["speed"])

    def _log(self, msg: str) -> None:
        self.data["log"].append({"t": _now(), "msg": msg})
        self.data["log"] = self.data["log"][-30:]

    def _save(self) -> None:
        if not self.data:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 状态推进 ---
    def tick(self) -> None:
        if not self.data:
            return
        cfg = self.data["config"]
        el = self._elapsed_min()
        if self.data["phase"] == "interaction" and el >= cfg["cycle_min"]:
            self._consolidate()
            self.data["phase"] = "silent"
            self._log("互动期结束 → 静默期（5 分钟内不检索、不提及）")
        if self.data["phase"] == "silent" and el >= cfg["cycle_min"] + cfg["silent_min"]:
            self._checkpoint()
            self.data["phase"] = "observed"
            if cfg.get("rehearse"):
                self.rehearse()
            self._log("第一次遗忘检查完成 → 进入观察期（无复述，等待二次检查）")
        if self.data["phase"] == "observed" and el >= cfg["cycle_min"] + cfg["silent_min"] + cfg["observe_min"]:
            self._checkpoint2()
            self.data["phase"] = "done"
        self._save()

    def _consolidate(self) -> None:
        mems = self.data["memories"]
        used: set[int] = set()
        merged = 0
        for i, a in enumerate(mems):
            if a["id"] in used:
                continue
            for b in mems[i + 1 :]:
                if b["id"] in used or b["state"] != "active":
                    continue
                if _jaccard(_chars(a["text"]), _chars(b["text"])) >= 0.85:
                    a["text"] += "；" + b["text"]
                    a["n"] += b["n"]
                    b["state"] = "merged"
                    used.add(b["id"])
                    merged += 1
        if merged:
            self._log(f"归纳：合并了 {merged} 条近似记忆")

    def _checkpoint(self) -> None:
        cfg = self.data["config"]
        kept = forgotten = 0
        for m in self.data["memories"]:
            if m["state"] not in ("active", "deepened"):
                continue
            if m.get("n_eff", m["n"]) > cfg["threshold"]:
                m["state"] = "kept"
                m["short"] = _shorten(m["text"])
                kept += 1
            else:
                m["state"] = "forgotten"
                forgotten += 1
        self._log(f"遗忘检查：保留 {kept} 条（已缩短），遗忘 {forgotten} 条")

    def _checkpoint2(self) -> None:
        """观察期结束的二次检查：双因子记忆值 S 低于 θ 才遗忘（验证高频保留的持久性）。"""
        cfg = self.data["config"]
        forgotten = 0
        for m in self.data["memories"]:
            if m["state"] != "kept":
                continue
            if self._S(m) < cfg["theta"]:
                m["state"] = "forgotten"
                forgotten += 1
        self._log(f"二次检查（S<{cfg['theta']}）：再遗忘 {forgotten} 条；其余保留")

    # --- 交互 ---
    def mention(self, mid: int, source: str = "user") -> tuple[bool, str]:
        """提及一个记忆。source: user / self / consolidate / implicit。"""
        self.tick()
        if not self.data:
            return False, "实验未开始"
        if self.data["phase"] != "interaction":
            return False, "当前不在互动期（静默期禁止提及）"
        cfg = self.data["config"]
        weights = {
            "user": 1.0,
            "self": cfg.get("self_weight", 0.4),
            "consolidate": cfg.get("consolidate_weight", 0.3),
            "implicit": 0.1,
        }
        weight = weights.get(source, 0.0)
        for m in self.data["memories"]:
            if m["id"] == mid:
                if m["state"] not in ("active", "deepened"):
                    return False, "该记忆当前不可提及"
                if source == "self":
                    el = self._elapsed_min()
                    last = m.get("last_self")
                    if last is not None and el - last < cfg.get("self_cooldown_min", 5.0):
                        return False, "自检索冷却中"
                    m["last_self"] = el
                if source == "user":
                    m["n"] += 1
                m["n_eff"] = m.get("n_eff", 0.0) + weight
                m["last_mention"] = _now()
                m["B"] *= 1.0 + 0.05 * weight
                if m["n_eff"] > cfg["threshold"] and m["state"] != "deepened":
                    m["state"] = "deepened"
                    self._log(f"记忆 #{mid} 有效复述 {m['n_eff']:.1f} 次 → 加深（{source}）")
                if m.get("tier") != "long" and m["n_eff"] >= cfg["promote_n"]:
                    m["tier"] = "long"
                    self._log(f"记忆 #{mid} 晋升长期层（有效复述 {m['n_eff']:.1f}）")
                self._save()
                return True, f"#{mid} 有效复述 {m['n_eff']:.2f}（{source}，+{weight:g}）"
        return False, "没有这条记忆"

    # --- 记忆值与视图 ---
    def _S(self, m: dict) -> float:
        cfg = self.data["config"]
        el = self._elapsed_min()
        n_eff = m.get("n_eff", m["n"])
        base_tau = cfg.get("tau_long_min", 10080.0) if m.get("tier") == "long" else cfg["tau0"]
        tau = base_tau * (1 + cfg["gamma"] * n_eff)
        return m["B"] * (1 + cfg["beta"] * math.log1p(n_eff)) * math.exp(-el / tau)

    def rehearse(self) -> None:
        """巩固复习：对已保留的记忆做一次「低权重复述」，模拟夜间重放。"""
        cfg = self.data["config"]
        boost = cfg.get("rehearse_boost", 0.5)
        touched = 0
        for m in self.data["memories"]:
            if m["state"] not in ("kept", "deepened", "active"):
                continue
            m["n_eff"] = m.get("n_eff", 0.0) + boost
            if m.get("tier") != "long" and m["n_eff"] >= cfg["promote_n"]:
                m["tier"] = "long"
            touched += 1
        self._log(f"巩固复习：{touched} 条记忆被重新激活（+{boost:g} 有效复述）")
        self._save()

    def state_view(self) -> dict:
        if not self.data:
            return {"started": False, "phase": "idle", "memories": [], "config": CFG_DEFAULT, "log": []}
        self.tick()
        cfg = self.data["config"]
        el = self._elapsed_min()
        total = cfg["cycle_min"] + cfg["silent_min"] + cfg["observe_min"]
        if self.data["phase"] == "interaction":
            remain = max(0.0, cfg["cycle_min"] - el)
        elif self.data["phase"] == "silent":
            remain = max(0.0, cfg["cycle_min"] + cfg["silent_min"] - el)
        elif self.data["phase"] == "observed":
            remain = max(0.0, total - el)
        else:
            remain = 0.0
        if self.data["phase"] in ("interaction", "silent", "observed"):
            last = float(self.data.get("last_sample", 0.0))
            if el - last >= 5.0 / 60.0:
                pts = [
                    [round(el, 3), m["id"], round(self._S(m), 4)]
                    for m in self.data["memories"]
                    if m["state"] != "merged"
                ]
                self.data.setdefault("history", []).extend(pts)
                self.data["history"] = self.data["history"][-3000:]
                self.data["last_sample"] = el
                self._save()
        max_s = max((self._S(m) for m in self.data["memories"]), default=0.001)
        mems = [
            {
                "id": m["id"],
                "text": m["text"],
                "short": m["short"],
                "kind": m["kind"],
                "n": m["n"],
                "n_eff": round(m.get("n_eff", m["n"]), 2),
                "tier": m.get("tier", "short"),
                "state": m["state"],
                "cluster": m.get("cluster", 0),
                "B": round(m["B"], 3),
                "S": round(self._S(m), 4),
                "Smax": round(max_s, 4),
            }
            for m in self.data["memories"]
            if m["state"] != "merged"
        ]
        clusters = []
        for c in self.data.get("clusters", []):
            members = [m for m in self.data["memories"] if m.get("cluster") == c["id"]]
            alive = [m for m in members if m["state"] in ("active", "deepened", "kept")]
            ss = [self._S(m) for m in alive]
            clusters.append(
                {
                    "id": c["id"],
                    "label": c["label"],
                    "size": len(members),
                    "alive": len(alive),
                    "avgS": round(sum(ss) / len(ss), 4) if ss else 0.0,
                }
            )
        return {
            "started": True,
            "phase": self.data["phase"],
            "elapsed_min": round(el, 2),
            "remaining_sec": round(remain * 60, 1),
            "config": cfg,
            "memories": mems,
            "clusters": clusters,
            "log": self.data["log"][-8:],
        }
