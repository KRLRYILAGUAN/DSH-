"""命令行入口：python -m neuron_memory <remember|recall|forget|consolidate|stats|demo>"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .memory import NeuronMemory, default_db_path


def _print_notes(rows: list[dict]) -> None:
    if not rows:
        print("（没有匹配的记忆）")
        return
    for r in rows:
        print(f"[{r['id']}] {r['score']:.3f}  ({r['type']})  {r['text']}")


def _demo(mem: NeuronMemory) -> None:
    print("== 1. remember：写入 6 条种子记忆 ==")
    seeds = [
        ("老大喜欢喝冰美式，不加糖", "preference", 0.8),
        ("老大让我把称呼从主人改成老大", "decision", 0.6),
        ("我的名字是鲸鱼娘，老大叫我小鲸", "fact", 0.9),
        ("老大想搭一个 AI 神经元记忆框架，自用、Python", "project", 0.7),
        ("记忆框架的核心接口是 remember/recall/forget/consolidate", "concept", 0.6),
        ("工作区里有个 底座标注分析 文件夹", "event", 0.3),
    ]
    for text, ntype, imp in seeds:
        nid, mode = mem.remember(text, ntype, imp)
        print(f"  #{nid} [{mode}]  {text}")

    print("\n== 2. recall：混合打分 + 关联扩散 ==")
    for q in ("老大怎么叫我", "老大喝什么", "记忆框架用什么语言写"):
        print(f"\n查询：{q}")
        _print_notes(mem.recall(q, k=3))

    print("\n== 3. consolidate：合并近似重复 ==")
    print(f"merged {mem.consolidate()}")

    print("\n== 4. forget：显示会被归档的陈旧记忆（dry-run）==")
    for r in mem.forget(stale=True, dry_run=True):
        print(f"  [{r['id']}] importance={r['importance']:.3f}  {r['text']}")

    print("\n== 5. stats ==")
    print(json.dumps(mem.stats(), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="neuron-memory", description="AI 神经元记忆框架 M1")
    ap.add_argument("--db", default=None, help="数据库路径（默认 ~/.neuron_memory/neuron.db）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("remember", help="记住一条")
    p.add_argument("text")
    p.add_argument("--type", default="fact", help="fact/preference/decision/project/concept/event…")
    p.add_argument("--importance", type=float, default=None, help="0~1，默认 0.6")
    p.add_argument("--episode", default=None, help="原始出处片段（来源链）")
    p.add_argument("--source", default="agent", help="episode 来源：user/session/agent/import")
    p.add_argument("--entity", action="append", default=None, help="实体名，可重复")

    p = sub.add_parser("persona", help="人格卡：show / add <text> / clear")
    p.add_argument("action", choices=["show", "add", "clear"])
    p.add_argument("text", nargs="?", default="")

    p = sub.add_parser("chat", help="记录一条闲聊摘要（低权重、快衰减）")
    p.add_argument("text")
    p.add_argument("--episode", default=None)

    p = sub.add_parser("recall", help="检索")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.add_argument("--as-of", default=None, help="按时间点回溯（如 2026-03-01 或 ISO 时间）")
    p.add_argument("--rerank", action="store_true", help="用 cross-encoder 重排（需 fastembed + 模型）")
    p.add_argument("--chat", action="store_true", help="包含闲聊流")

    p = sub.add_parser("forget", help="遗忘：归档陈旧记忆，或硬删除指定 id")
    p.add_argument("--stale", action="store_true", help="归档低重要度 + 长期未用的记忆")
    p.add_argument("--id", type=int, default=None, help="硬删除指定 id")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("mention", help="给一条记忆加一次提及（来源可指定）")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--source", default="user", help="user / self / consolidate / implicit")

    sub.add_parser("rehearse", help="巩固复习：对重要记忆做一次低权重复述")

    p = sub.add_parser("restore", help="恢复已归档/被取代的记忆")
    p.add_argument("--id", type=int, required=True)

    p = sub.add_parser("history", help="查看 raw 事件记录（可指定记忆 id）")
    p.add_argument("--id", type=int, default=None)

    p = sub.add_parser("bridge", help="只读桥接：从 DSH 记忆库导入 markdown 事实")
    p.add_argument("--dir", default=None, help="DSH 记忆目录（默认 ~/.memory）")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("extract", help="从对话文本抽取候选事实（规则版）")
    p.add_argument("--text", default=None)
    p.add_argument("--file", default=None)
    p.add_argument("--apply", action="store_true", help="抽取后直接写入记忆")
    p.add_argument("--type", default="fact")
    p.add_argument("--importance", type=float, default=0.6)

    sub.add_parser("consolidate", help="合并重复记忆")
    p = sub.add_parser("backup", help="备份数据库（在线一致备份）")
    p.add_argument("--out", default=None, help="备份文件路径，默认 <db目录>/backups/neuron-时间戳.db")
    p = sub.add_parser("restore-db", help="用备份覆盖当前数据库（会先自动安全备份）")
    p.add_argument("file")
    p.add_argument("--yes", action="store_true", help="确认覆盖")
    sub.add_parser("stats", help="看统计")
    sub.add_parser("demo", help="跑一遍完整演示")

    args = ap.parse_args(argv)

    if args.cmd == "demo":
        db = args.db or str(Path.cwd() / "data" / "demo.db")
        Path(db).unlink(missing_ok=True)
    else:
        db = args.db or str(default_db_path())

    reranker = None
    if getattr(args, "rerank", False):
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            model = os.environ.get("NEURON_RERANK_MODEL", "BAAI/bge-reranker-base")
            cache = os.environ.get("NEURON_RERANK_CACHE") or None
            reranker = TextCrossEncoder(model, cache_dir=cache)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: reranker unavailable ({exc}); falling back to hybrid recall")

    mem = NeuronMemory(db, reranker=reranker)

    if args.cmd == "remember":
        try:
            nid, mode = mem.remember(
                args.text, args.type, args.importance,
                episode=args.episode, source=args.source, entities=args.entity,
            )
        except ValueError as exc:
            print(f"error: {exc}")
            raise SystemExit(1)
        print(f"#{nid} {mode}")
    elif args.cmd == "persona":
        if args.action == "add":
            if not args.text.strip():
                print("error: persona add 需要文本")
                raise SystemExit(1)
            nid, mode = mem.persona_add(args.text)
            print(f"#{nid} {mode} (pinned)")
        elif args.action == "clear":
            ids = mem.persona_clear()
            print("cleared:", ids or "nothing")
        else:
            rows = mem.persona_show()
            if not rows:
                print("(empty persona)")
            for r in rows:
                print(f"#{r['id']} {r['text']}")
    elif args.cmd == "chat":
        nid, mode = mem.remember_chat(args.text, args.episode)
        print(f"#{nid} {mode} (chat)")
    elif args.cmd == "recall":
        rows = mem.recall(args.query, args.k, as_of=args.as_of, rerank=args.rerank, include_chat=args.chat)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_notes(rows)
    elif args.cmd == "forget":
        if args.id is not None:
            mem.forget_one(args.id)
            print(f"deleted #{args.id}")
        else:
            rows = mem.forget(stale=True, dry_run=args.dry_run)
            verb = "would archive" if args.dry_run else "archived"
            print(f"{verb} {len(rows)}")
            for r in rows:
                print(f"  [{r['id']}] importance={r['importance']:.3f}  {r['text']}")
    elif args.cmd == "mention":
        ok, msg = mem.mention(args.id, args.source)
        print(msg)
    elif args.cmd == "rehearse":
        print(f"rehearsed {mem.rehearse()}")
    elif args.cmd == "restore":
        print("restored" if mem.restore(args.id) else "not found")
    elif args.cmd == "history":
        events = mem.store.raw_events(args.id)
        if not events:
            print("（没有记录）")
        for e in events:
            print(f"[{e['ts']}] {e['kind']:<9} #{e['note_id']}  {e['text'] or ''}  {e['meta'] or ''}")
    elif args.cmd == "backup":
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path(args.out) if args.out else Path(db).parent / "backups" / f"neuron-{ts}.db"
        dest = mem.store.backup(out)
        print(f"backup: {dest}")
    elif args.cmd == "restore-db":
        src = Path(args.file)
        if not src.exists():
            print(f"missing: {src}")
            raise SystemExit(1)
        if not args.yes:
            print("restore-db 会用备份覆盖当前库；确认请加 --yes")
            raise SystemExit(1)
        safety = Path(db).with_name(f"{Path(db).stem}.bak-{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(db, safety)
        mem.store.close()
        shutil.copy2(src, db)
        for suffix in ("-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
        print(f"restored: {db}")
        print(f"safety:   {safety}")
    elif args.cmd == "bridge":
        from .bridge import import_memory

        src = args.dir or os.environ.get("DSH_MEMORY_DIR") or str(Path.home() / ".memory")
        stats = import_memory(mem, src, dry_run=args.dry_run)
        print(f"source: {src}")
        print(f"files={stats['files']} facts={stats['facts']} imported={stats['imported']} skipped={stats['skipped']}")
    elif args.cmd == "extract":
        from .extract import extract_facts

        if args.file:
            text = Path(args.file).read_text("utf-8")
        elif args.text:
            text = args.text
        else:
            print("error: 需要 --text 或 --file")
            raise SystemExit(1)
        facts = extract_facts(text)
        for f in facts:
            if args.apply:
                nid, mode = mem.remember(f, args.type, args.importance)
                print(f"#{nid} [{mode}] {f}")
            else:
                print(f"- {f}")
        if not facts:
            print("（没有抽到候选事实）")
    elif args.cmd == "consolidate":
        print(f"merged {mem.consolidate()}")
    elif args.cmd == "stats":
        print(json.dumps(mem.stats(), ensure_ascii=False, indent=2))
    elif args.cmd == "demo":
        _demo(mem)


if __name__ == "__main__":
    main()
