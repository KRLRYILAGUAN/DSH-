"""从对话文本里抽取候选事实（规则版，离线可用）。

用法：
  python -m neuron_memory extract --text "老大：我叫老大，喜欢喝冰美式。"
  python -m neuron_memory extract --file data/chat_demo.txt --apply
"""

from __future__ import annotations

import re

SPEAKER_RE = re.compile(r"^\s*(?:\[[^\]]+\]\s*)?([\w\u4e00-\u9fff]{1,12})\s*[:：]\s*(.+)$")
SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")
QUESTION_END = re.compile(r"[?？]\s*$")

# 出现这些词才当事实候选（够用即可，宁可少抽不错抽）
FACT_HINTS = (
    "喜欢", "爱", "讨厌", "名字", "叫", "生日", "住在", "工作", "要", "想",
    "有", "喝", "吃", "用", "改", "不", "做", "习惯",
    "i ", "my ", "i'm", "i am", "prefer", "like", "love", "hate", "live",
    "work", "called", "name",
)
# 明显的请求/指令，不当事实
COMMAND_HINTS = ("帮我", "请你", "麻烦", "能不能", "去把", "给我", "please", "can you")
# 应答/客套，不当事实
ACK_PREFIXES = ("好的", "嗯", "收到", "明白", "ok", "okay", "got it", "sure", "yes")


def _clean(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s.strip().strip("。！？!?；;，, ")


def extract_facts(text: str, limit: int = 50) -> list[str]:
    text = text.lstrip("\ufeff")
    facts: list[str] = []
    for line in text.splitlines():
        m = SPEAKER_RE.match(line)
        body = m.group(2) if m else line
        for sent in SENT_SPLIT.split(body):
            raw = sent.strip()
            if not raw or QUESTION_END.search(raw):
                continue
            s = _clean(raw)
            low = s.lower()
            if len(s) < 4:
                continue
            if any(low.startswith(p) for p in ACK_PREFIXES):
                continue
            if any(c in low for c in COMMAND_HINTS) and any(w in low for w in ("你", "you")):
                continue
            if not any(h in low for h in FACT_HINTS):
                continue
            if s in facts:
                continue
            facts.append(s)
            if len(facts) >= limit:
                return facts
    return facts
