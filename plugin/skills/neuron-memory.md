# neuron-memory (filesystem skill reference)

This file mirrors the skill registered by `dsh-plugin-neuron-memory`. The
plugin's `lib/skill.js` is the source of truth; keep this copy in sync when the
protocol changes.

## Commands

- `remember "<fact>" [--type ...] [--importance 0.8]`
- `recall "<query>" [-k 5] [--as-of ISO_TIME]`
- `mention <id> [--source user|self|consolidate|implicit]`
- `rehearse <id>` / `forget <id>` / `restore <id>`
- `history <id>` / `stats` / `consolidate`
- `bridge --dir ~/.memory` (optional read-only import)

## Protocol

1. Recall before answering questions that may depend on past context; paraphrase
   the question instead of pasting the raw sentence.
2. Remember durable facts, preferences and decisions; skip banter and tool noise.
3. When the user corrects an old value, remember the new value — supersede keeps
   history.
4. Never invent memories; if recall is empty, say so.
5. `forget` only on explicit request.
