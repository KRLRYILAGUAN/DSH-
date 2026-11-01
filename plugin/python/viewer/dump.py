"""Dump the viewer graph as JSON for the DSH plugin route."""

from __future__ import annotations

import json
import sys

from viewer.server import load_graph


def main() -> None:
    graph = load_graph(sys.argv[1])
    sys.stdout.buffer.write(json.dumps(graph, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
