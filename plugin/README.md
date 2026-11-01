# neuron-memory

<p align="center">
  Long-term memory for DeepSeek Harness — SQLite + hybrid recall + decay,
  packaged as a DSH bundle plugin.
</p>

The plugin is a thin shell: it registers the `neuron-memory` skill, ships a
CLI bridge and a brain-region viewer. Memory logic, storage and retrieval stay
in the Python `neuron_memory` core under `python/`.

## Capabilities

| Surface | What it does |
|---|---|
| Skill `neuron-memory` | Tells the agent when and how to remember/recall; includes write-time extraction, idle checkpoint and wrap-up protocol |
| CLI `dsh-neuron-memory` | `remember` / `recall` / `chat` / `persona` / `mention` / `rehearse` / `forget` / `restore` / `history` / `stats` / `consolidate` / `backup` / `restore-db` |
| Viewer | Local dashboard on `:8420`: nebula/brain views, per-node forgetting curve, chat stream, provenance |
| Client entry | Header button “记忆” + Settings status card (opens the viewer in a new tab) |

## Memory model

- SQLite tables: `notes`, `links`, `episodes`, `entities`, `raw_events`, `meta`
- Hybrid recall: embedding + BM25 + entity match + memory value + recency + literal overlap
- Value `S = importance · (1 + 0.5·ln(1+n_eff)) · exp(−t/τ)`; τ depends on tier,
  `n_eff` and brain region
- Supersede keeps history; links carry `valid_from` / `valid_to`; deleting an
  edge is never required
- Optional `--rerank` cross-encoder (see below)

## Requirements

- Node.js >= 18
- Windows x64: bundled CPython 3.12 + `neuron_memory` (no system Python)
- Other platforms: `NEURON_PYTHON=/usr/bin/python3 NEURON_HOME=/path/to/core`

Optional overrides: `NEURON_PYTHON`, `NEURON_HOME`, `NEURON_DB`.

## Install

Official desktop flow: **Settings → Plugins → Add plugin**, enter a tarball
path, then **enable** the plugin (installing alone does not mount it).

```text
C:\Users\Lenovo\.dsh\plugin-cache\neuron-memory.tgz
```

Upgrade: overwrite the same ASCII tarball path and re-add/update in Settings.
Do **not** run `pnpm add` inside the profile or hand-edit its `package.json`
(DSH locks the file while running, and non-ASCII paths get corrupted).

This is a bundle + client plugin: Node-half changes need a web restart, client
changes need a page refresh.

## CLI

```powershell
dsh-neuron-memory remember "用户希望被称呼为老大" --type preference --importance 0.9
dsh-neuron-memory recall "称呼" -k 5
dsh-neuron-memory chat "聊了会儿周末计划，气氛轻松"
dsh-neuron-memory persona show
dsh-neuron-memory stats
```

`remember` accepts `--episode "原文片段"` for provenance and `--entity Name`
(repeatable) for the entity layer. `chat` writes to the fast-decay, hidden-by-
default chat stream. `persona` manages the pinned identity card (never decays).

## Viewer

Standalone local service at `http://127.0.0.1:8420`, started by the plugin host
on mount. Open it from the header “记忆” button or the Settings card; there is
no iframe and no DSH web route.

## Optional reranker

```powershell
node scripts/setup-rerank.mjs
```

Installs `fastembed` into `python/vendor` using the bundled Python (~100 MB
unpacked). Caveats: needs network for wheels and a HuggingFace-reachable
network/model cache; vendoring fastembed also makes the embedder auto-detect
it, so keep the default hash embedder if you have no cache.

## Config

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | master switch |
| `registerSkill` | `true` | register the skill |
| `pythonHome` | `$NEURON_HOME` or package `python/` | directory containing `neuron_memory` |
| `dbPath` | `$NEURON_DB` or `<workspace>/.neuron-memory/neuron.db` | SQLite path |
| `viewerPort` | `8420` | viewer port |

## Limitations

- Bundled interpreter is **Windows x64 only**; other platforms must provide
  Python and `neuron_memory`.
- No LLM-based extraction inside the plugin: the agent decides what to write
  through the skill.
- Entity edges are not built automatically (dense edges previously hurt recall);
  `build_entity_links` remains available for experiments.
- Viewer is localhost-only, single-workspace DB per workspace.

## Test

```powershell
node --test
node --test --test-isolation=none   # restricted sandbox
```

Covers skill registration, disabled/no-service paths, env resolution, argv
building, package/patch presence.

## Data

Default DB: `<workspace>/.neuron-memory/neuron.db`. Delete the folder to wipe
facts; `dsh-neuron-memory backup` writes a timestamped copy.
