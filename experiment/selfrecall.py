"""实验 B：自检索与巩固复习对长期记忆的影响。

场景：老大两处提到「称呼」（记忆 #2），我回答里也常用到它。
对照：只算用户提及 / 加上自检索（0.4）/ 再加巩固复习（+0.5）。
长期层半衰期按 90 天算，看 1 年后还剩几条。

用法：python -m experiment.selfrecall
"""

from __future__ import annotations

import math
import time
from pathlib import Path

from .engine import Experiment

USER_PLAN = {1: 3, 2: 2, 3: 3, 5: 2, 7: 3, 9: 1, 11: 2}
SELF_PLAN = {2: 3, 1: 1, 3: 1, 7: 1}  # 我在回答里真的用到这些记忆
HORIZON_MIN = 525600  # 1 年


def _s_at(m: dict, minutes: int, cfg: dict) -> float:
    n = m.get("n_eff", m["n"])
    base = cfg["tau_long_min"] if m.get("tier") == "long" else cfg["tau0"]
    tau = base * (1 + cfg["gamma"] * n)
    return m["B"] * (1 + cfg["beta"] * math.log1p(n)) * math.exp(-minutes / tau)


def run_variant(name: str, use_self: bool, use_rehearse: bool) -> dict:
    path = Path(f"experiment/data/sr_{abs(hash(name)) % 100000}.json")
    path.unlink(missing_ok=True)
    e = Experiment(path)
    e.start(1.0)
    cfg = e.data["config"]
    cfg.update(
        {
            "tau_long_min": 129600.0,   # 长期层 90 天
            "self_cooldown_min": 0.0,   # 模拟时取消冷却，允许快速连续自检索
            "rehearse": False,
        }
    )
    for mid, times in USER_PLAN.items():
        for _ in range(times):
            e.mention(mid, "user")
    if use_self:
        for mid, times in SELF_PLAN.items():
            for _ in range(times):
                ok, msg = e.mention(mid, "self")
    e.data["t0_ts"] = time.time() - 15.1 * 60
    e.tick()
    if use_rehearse:
        e.rehearse()
    kept = [m for m in e.data["memories"] if m["state"] == "kept"]
    mem2 = next(m for m in e.data["memories"] if m["id"] == 2)
    alive = sum(1 for m in kept if _s_at(m, HORIZON_MIN, cfg) >= cfg["theta"])
    out = {
        "variant": name,
        "kept@15": len(kept),
        "mem2": mem2["state"],
        "mem2_n_eff": round(mem2.get("n_eff", mem2["n"]), 2),
        "mem2_tier": mem2.get("tier", "short"),
        "mem2_S@1y": round(_s_at(mem2, HORIZON_MIN, cfg), 3),
        "alive@1y": alive,
    }
    path.unlink(missing_ok=True)
    return out


def main() -> None:
    variants = [
        ("仅用户提及", False, False),
        ("用户 + 自检索", True, False),
        ("用户 + 自检索 + 巩固", True, True),
    ]
    print(f"{'方案':<22}{'kept@15':>9}{'#2 状态':>10}{'#2 n_eff':>9}{'#2 层':>7}{'#2 S@1y':>9}{'存活@1y':>9}")
    for name, use_self, use_rehearse in variants:
        r = run_variant(name, use_self, use_rehearse)
        print(
            f"{r['variant']:<22}{r['kept@15']:>9}{r['mem2']:>10}{r['mem2_n_eff']:>9}"
            f"{r['mem2_tier']:>7}{r['mem2_S@1y']:>9}{r['alive@1y']:>9}"
        )


if __name__ == "__main__":
    main()
