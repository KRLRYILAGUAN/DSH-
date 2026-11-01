"""实验台命令行：聊天里也能对记忆做「提及」操作。

用法：
  python -m experiment.cli status
  python -m experiment.cli start --speed 1
  python -m experiment.cli start --speed 60   # 快进测试
  python -m experiment.cli mention --id 3
  python -m experiment.cli reset
"""

from __future__ import annotations

import argparse
import json
import urllib.request


def _get(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


def _post(port: int, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _print_state(st: dict) -> None:
    if not st.get("started"):
        print("实验未开始")
        return
    print(f"阶段: {st['phase']}  剩余: {st['remaining_sec']:.0f}s  配置: {st['config']['threshold']} 次阈值")
    for m in st["memories"]:
        print(f"  #{m['id']:>2} n={m['n']} S={m['S']:.3f} [{m['state']}] {m['text'][:24]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8410)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("start")
    p.add_argument("--speed", type=float, default=1.0)
    p = sub.add_parser("mention")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--source", default="user", help="user / self / consolidate / implicit")
    sub.add_parser("reset")
    args = ap.parse_args()

    if args.cmd == "status":
        _print_state(_get(args.port, "/api/state"))
    elif args.cmd == "start":
        _print_state(_post(args.port, "/api/start", {"speed": args.speed}))
    elif args.cmd == "mention":
        r = _post(args.port, "/api/mention", {"id": args.id, "source": args.source})
        print(r["msg"])
    elif args.cmd == "reset":
        _post(args.port, "/api/reset", {})
        print("已重置")


if __name__ == "__main__":
    main()
