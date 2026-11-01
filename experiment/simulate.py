"""实验 A：时间常数 τ0 对照 + 长期尺度外推。

用法：python -m experiment.simulate
"""

from __future__ import annotations

import csv
import math
import time
from pathlib import Path

from .engine import Experiment

PLAN = {1: 3, 2: 2, 3: 3, 4: 1, 5: 2, 7: 3, 9: 1, 11: 2}
THETAS = (0.15, 0.30)
TAUS = (10.0, 20.0, 40.0)


def _simulate(tau0: float, theta: float, path: Path) -> dict:
    e = Experiment(path)
    e.start(1.0)
    e.data["config"]["tau0"] = tau0
    e.data["config"]["theta"] = theta
    for mid, times in PLAN.items():
        for _ in range(times):
            e.mention(mid)
    # 快进到 15 分钟：第一次检查
    e.data["t0_ts"] = time.time() - 15.1 * 60
    e.tick()
    kept15 = [m for m in e.data["memories"] if m["state"] in ("kept", "active", "deepened")]
    # 快进到 45 分钟：二次检查（θ 生效）
    e.data["t0_ts"] = time.time() - 45.1 * 60
    e.tick()
    kept45 = [m for m in e.data["memories"] if m["state"] in ("kept", "active", "deepened")]
    s45 = [round(e._S(m), 3) for m in kept45]
    out = {
        "tau0": tau0,
        "theta": theta,
        "kept15": len(kept15),
        "kept45": len(kept45),
        "s45_min": min(s45) if s45 else 0.0,
        "s45_max": max(s45) if s45 else 0.0,
    }
    return out


def _crossing_table() -> list[dict]:
    """无复述情况下，S 从初始值衰减到 θ 所需时间（解析解）。"""
    rows = []
    beta, gamma = 0.5, 0.5
    for tau0 in (20.0, 60.0, 1440.0, 10080.0, 43200.0):
        row = {"tau0_min": tau0}
        for n in (0, 2, 5, 10):
            s0 = 0.7 * (1 + beta * math.log1p(n))
            tau = tau0 * (1 + gamma * n)
            t = tau * math.log(s0 / 0.15)
            row[f"n={n}"] = round(t, 1)
        rows.append(row)
    return rows


def main() -> None:
    print("== A. τ0 对照（同一提及计划，15 与 45 分钟检查）==")
    rows = []
    for tau0 in TAUS:
        for theta in THETAS:
            p = Path(f"experiment/data/sim_tau{int(tau0)}_th{int(theta*100)}.json")
            p.unlink(missing_ok=True)
            r = _simulate(tau0, theta, p)
            rows.append(r)
            print(
                f"  τ0={tau0:>4}min θ={theta:.2f}  kept@15={r['kept15']:>2}  "
                f"kept@45={r['kept45']:>2}  S(45)∈[{r['s45_min']:.2f}, {r['s45_max']:.2f}]"
            )
            p.unlink(missing_ok=True)

    print("\n== B. 长期外推：S 衰减到 θ=0.15 所需时间（分钟，无复述）==")
    print("  τ0(分钟)   n=0      n=2      n=5      n=10")
    for r in _crossing_table():
        print(
            f"  {r['tau0_min']:>9.0f}  {r['n=0']:>8.0f}  {r['n=2']:>8.0f}  "
            f"{r['n=5']:>8.0f}  {r['n=10']:>8.0f}"
        )

    out = Path("experiment/data/simulate_result.csv")
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n结果已存 {out}")


if __name__ == "__main__":
    main()
