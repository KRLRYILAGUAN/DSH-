"""嵌入层：默认哈希 n-gram 兜底；装了 fastembed 就用 ONNX 真向量（自动检测）。"""

from __future__ import annotations

import hashlib
import math
import os
import re
import sys
from pathlib import Path

DIM = 512

# Optional vendored deps (e.g. fastembed installed by scripts/setup-rerank.mjs).
_VENDOR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.append(str(_VENDOR))


def _grams(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    words = re.findall(r"[a-z0-9]+", text)
    grams: list[str] = []
    for i in range(len(cjk) - 1):
        grams.append(cjk[i] + cjk[i + 1])
    grams.extend(cjk)
    grams.extend(w for w in words if len(w) >= 2)
    return grams or [text or "empty"]


class HashEmbedder:
    """字符 n-gram 哈希向量。便宜、离线、零依赖，做兜底。"""

    name = "hash-char-ngram"

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for gram in set(_grams(text)):
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            vec[h % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)


class FastEmbedder:
    """fastembed（ONNX）真向量后端；模型缓存在项目 data/models 内，删文件夹即清。"""

    def __init__(self, model_name: str | None = None, cache_dir: str | Path | None = None):
        from fastembed import TextEmbedding

        self.model_name = model_name or os.environ.get(
            "NEURON_MODEL", "BAAI/bge-small-zh-v1.5"
        )
        cache = Path(cache_dir) if cache_dir else Path(__file__).resolve().parents[1] / "data" / "models"
        self.model = TextEmbedding(model_name=self.model_name, cache_dir=str(cache))
        self.name = f"fastembed:{self.model_name.split('/')[-1]}"

    def embed(self, text: str) -> list[float]:
        return list(self.model.embed([text]))[0].tolist()

    def embed_query(self, text: str) -> list[float]:
        """BGE 类模型查询侧需要检索指令前缀，fastembed 的 query_embed 会处理。"""
        return list(self.model.query_embed([text]))[0].tolist()


def get_embedder(name: str | None = None):
    name = (name or os.environ.get("NEURON_EMBEDDER") or "auto").lower()
    if name == "hash":
        return HashEmbedder()
    if name == "fastembed":
        return FastEmbedder()
    try:
        return FastEmbedder()
    except Exception:
        return HashEmbedder()
