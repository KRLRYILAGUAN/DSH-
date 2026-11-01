"""打印真实 token 用量（本会话 / 今日 / 全部）。"""

from __future__ import annotations

import json

from experiment.tokens import scan_sessions


def main() -> None:
    t = scan_sessions()
    print(f"会话数: {t['sessions']}")
    print(f"本会话: 输入 {t['current']['input']:,} · 输出 {t['current']['output']:,}")
    print(f"今日:   输入 {t['today']['input']:,} · 输出 {t['today']['output']:,}")
    print(f"全部:   输入 {t['input']:,} · 输出 {t['output']:,} · 缓存读 {t['cache_read']:,} · 缓存写 {t['cache_write']:,}")


if __name__ == "__main__":
    main()
