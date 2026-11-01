"""回归基线：跑核心测试并和阈值比较，低于基线返回非零。

用法：
  python -m scripts.regress
  python -m scripts.regress --update   # 用当前结果刷新基线
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "data" / "regress_baseline.json"

THRESHOLDS = {
    "selftest": 21,
    "region": 16,
    "conflict": 0.95,
    "hit1": 0.50,
    "hit3": 0.60,
    "mrr": 0.60,
    "locomo10": 0.55,
}


def run(module: str, *extra: str, env: dict | None = None) -> str:
    merged = None
    if env:
        import os
        merged = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, "-m", module, *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged,
    )
    if proc.returncode != 0 and module != "scripts.conflict_eval":
        return proc.stdout + proc.stderr
    return proc.stdout + proc.stderr


def parse(out: str) -> dict:
    res = {}
    m = re.search(r"(\d+)/(\d+) passed", out)
    if m:
        res["selftest"] = int(m.group(1))
    m = re.search(r"RESULT (\d+) passed", out)
    if m:
        res["region"] = int(m.group(1))
    m = re.search(r"accuracy=([\d.]+)", out)
    if m:
        res["conflict"] = float(m.group(1))
    for key, pattern in (("hit1", r"hit@1: ([\d.]+)"), ("hit3", r"hit@3: ([\d.]+)"), ("mrr", r"mrr@5: ([\d.]+)")):
        m = re.search(pattern, out)
        if m:
            res[key] = float(m.group(1))
    m = re.search(r"@10=([\d.]+)", out)
    if m:
        res["locomo10"] = float(m.group(1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--locomo", action="store_true", help="additionally run LoCoMo2 subset (~2 min)")
    args = ap.parse_args()

    parts = [
        run("scripts.selftest"),
        run("scripts.region_eval"),
        run("scripts.conflict_eval"),
        run("scripts.eval", "--embedder", "hash"),
    ]
    if args.locomo:
        parts.append(run(
            "scripts.locomo_eval", "--limit", "2", "--embedder", "fastembed", "--mode", "baseline",
            env={"NEURON_MODEL": "BAAI/bge-small-en-v1.5", "HF_ENDPOINT": "https://hf-mirror.com"},
        ))
    out = "\n".join(parts)
    got = parse(out)
    if "selftest" not in got:
        print("selftest output tail:\n" + out[-1200:])
    base = json.loads(BASELINE.read_text("utf-8")) if BASELINE.exists() else THRESHOLDS
    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(got, ensure_ascii=False, indent=2), "utf-8")
        print("baseline updated:", got)
        return

    failed = []
    print(f"{'metric':<10} {'got':>6} {'min':>6}")
    for key, minimum in base.items():
        value = got.get(key)
        ok = value is not None and value >= minimum
        print(f"{key:<10} {str(value):>6} {minimum:>6} {'ok' if ok else 'FAIL'}")
        if not ok:
            failed.append(key)
    if failed:
        print("regression:", ", ".join(failed))
        raise SystemExit(1)
    print("all metrics above baseline")


if __name__ == "__main__":
    main()
