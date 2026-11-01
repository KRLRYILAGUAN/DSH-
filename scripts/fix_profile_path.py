"""One-shot repair for the desktop profile's neuron-memory dependency path.

Run this only while DSH is fully closed. It rewrites the corrupted (mojibake)
file: path to a stable ASCII tarball path and keeps a timestamped backup.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROFILE = Path(os.environ.get("NEURON_PROFILE", Path.home() / ".dsh" / "profiles" / "desktop"))
PKG = PROFILE / "package.json"
CACHE = Path.home() / ".dsh" / "plugin-cache" / "neuron-memory.tgz"
DEP = "dsh-plugin-neuron-memory"
TARGET = "file:C:/Users/Lenovo/.dsh/plugin-cache/neuron-memory.tgz"


def main() -> int:
    if not PKG.exists():
        print(f"missing: {PKG}")
        return 1
    if not CACHE.exists():
        print(f"missing tarball: {CACHE}")
        return 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = PKG.with_name(f"package.json.bak-{stamp}")
    shutil.copy2(PKG, backup)
    data = json.loads(PKG.read_text("utf-8"))
    deps = data.setdefault("dependencies", {})
    old = deps.get(DEP)
    deps[DEP] = TARGET
    PKG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"backup: {backup}")
    print(f"old: {old}")
    print(f"new: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
