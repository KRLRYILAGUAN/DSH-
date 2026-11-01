"""长期记忆对照：单层 vs 多尺度（长期层）+ 定期复习，看能否撑到 1 年。

用法：python -m experiment.longterm
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from .engine import Experiment

PLAN = {1: 3, 2: 2, 3: 3, 4: 1, 5: 2, 7: 3, 9: 1, 11: 2}
KEPT_IDS = (1, 3, 7)
HORIZONS = [("1h", 60), ("1d", 1440), ("7d", 10080), ("30d", 43200), ("90d", 129600), ("1y", 525600)]

VARIANTS = [
    ("单层 20min", {"tau_long_min": 20.0, "promote_n": 9999}),
    ("长期层 7d", {"tau_long_min": 10080.0}),
    ("长期层 30d", {"tau_long_min": 43200.0}),
    ("长期层 90d", {"tau_long_min": 129600.0}),
    ("长期层 30d + 每月复习", {"tau_long_min": 43200.0, "rehearse_every_days": 30}),
    ("长期层 90d + 半年复习", {"tau_long_min": 129600.0, "rehearse_every_days": 182}),
]


def run_variant(name: str, overrides: dict) -> dict:
    path = Path(f"experiment/data/lt_{abs(hash(name)) % 100000}.json")
    path.unlink(missing_ok=True)
    e = Experiment(path)
    e.start(1.0)
    cfg = e.data["config"]
    for k, v in overrides.items():
        if k != "rehearse_every_days":
            cfg[k] = v
    for mid, times in PLAN.items():
        for _ in range(times):
            e.mention(mid)
    # 快进到 15 分钟（第一次检查完成）
    e.data["t0_ts"] = time.time() - 15.1 * 60
    e.tick()
    mems = [m for m in e.data["memories"] if m["id"] in KEPT_IDS]
    every = overrides.get("rehearse_every_days")
    if every:
        reps = int(365 // every)
        for m in mems:
            m["n_eff"] = m.get("n_eff", m["n"]) + 0.5 * reps
    row = {}
    for label, mins in HORIZONS:
        alive = 0
        for m in mems:
            n = m.get("n_eff", m["n"])
            base = cfg["tau_long_min"] if m.get("tier") == "long" else cfg["tau0"]
            tau = base * (1 + cfg["gamma"] * n)
            s = m["B"] * (1 + cfg["beta"] * math.log1p(n)) * math.exp(-mins / tau)
            if s >= cfg["theta"]:
                alive += 1
        row[label] = alive
    path.unlink(missing_ok=True)
    return row


def main() -> None:
    labels = [h[0] for h in HORIZONS]
    print("== 保留记忆（1/3/7）在时间尺度上的存活数（/3）==")
    print(f"{'方案':<20}" + "".join(f"{l:>6}" for l in labels))
    for name, overrides in VARIANTS:
        row = run_variant(name, overrides)
        print(f"{name:<20}" + "".join(f"{row[l]:>6}" for l in labels))


if __name__ == "__main__":
    main()
