/**
 * Skill text for dsh-plugin-neuron-memory.
 *
 * The skill is a protocol document: it teaches the agent when and how to call
 * the Python memory core. No memory logic lives here.
 */

export const NEURON_SKILL_NAME = 'neuron-memory'

export const NEURON_SKILL_DESCRIPTION =
  'Neuron-style long-term memory: remember facts, recall by hybrid search, rehearse/forget, and browse the memory graph.'

export const NEURON_SKILL_WHEN_TO_USE =
  'When the user shares a durable fact, preference, decision or project detail that should survive this session; when a question may depend on earlier context; when the user asks what you remember or asks you to forget something.'

export function skillContent({ pythonHome, dbPath } = {}) {
  const home = pythonHome || '<NEURON_HOME>'
  const db = dbPath || '<NEURON_DB>'
  const exe = process.platform === 'win32'
    ? `${home}\\runtime\\python.exe`
    : `${home}/runtime/bin/python3`
  const bridge = `${home}/../scripts/cli.mjs`
  return `# neuron-memory

Long-term memory backed by the Python \`neuron_memory\` package. The core is a
SQLite store with hybrid recall (embedding + BM25 + entities + memory value),
dual-factor decay, long-term tier and supersede/history.

## Environment

- Python home (contains the \`neuron_memory\` package): \`${home}\`
- Bundled interpreter: \`${exe}\`
- Database: \`NEURON_DB\` if set, otherwise \`./.neuron-memory/neuron.db\`
  relative to the current working directory (a workspace-local default that
  works under the DSH sandbox).
- CLI bridge (recommended; works from any directory): \`node "${bridge}"\`
- Viewer (standalone): \`http://127.0.0.1:8420\` — the plugin host starts it;
  the Settings panel embeds it on demand (no shortcut needed)

## Commands

Preferred — the bridge sets PYTHONPATH and handles the database fallback:

\`node "${bridge}" <command>\`

Direct interpreter (requires \`cd\` to the Python home):

\`cd "${home}"; "${exe}" -m neuron_memory --db "${db}" <command>\`

- \`remember "<fact>" [--type fact|preference|decision|project|concept|event] [--importance 0.8]\`
- \`recall "<query>" [-k 5] [--as-of 2026-10-01T00:00:00]\`
- \`mention <id> [--source user|self|consolidate|implicit]\`
- \`rehearse <id>\` — spaced repetition consolidation
- \`forget <id>\` / \`restore <id>\`
- \`stats\` — counts by tier / active / archived
- \`persona show\` / \`persona add "<text>"\` / \`persona clear\` — persona card (pinned, never decays)
- \`chat "<gist>"\` — casual chat log (low weight, fast decay, excluded from normal recall)
- \`history <id>\` — supersede chain
- \`bridge --dir ~/.memory\` — optional read-only import from a markdown memory store
- \`consolidate\` — merge near-duplicates
- \`demo\` — smoke test

## Protocol

0. At session start, run \`persona show\`. If it returns items, follow them as
   the assistant's identity/style card. Change it only when the user explicitly
   asks (then \`persona add\`/\`persona clear\`); never rewrite it silently.
   Casual chat: after every purely casual exchange (no durable fact), append
   one \`chat\` note with a one-sentence gist (not verbatim). Merge consecutive
   turns on the same topic into one note instead of one per message.
1. Before answering a question that may depend on past context, call
   \`recall\` with a short paraphrase of the question (not the raw sentence).
2. When the user states a durable fact, preference or decision, call
   \`remember\` with a concise third-person statement. Do not store banter,
   one-off commands or tool output.
3. If recall returns an older value contradicted by the user, call
   \`remember\` with the new value; the store's supersede rules keep history.
4. Never invent memories: if recall returns nothing, say so.
5. Reading is safe; \`forget\` is destructive and needs an explicit user request.
6. Write-time extraction: when the user states a durable fact, preference or
   decision, call \`remember\` right away (1-3 statements). Do not wait for the
   session to end.
7. Idle checkpoint: after delivering a substantive task, or at a natural pause,
   scan the recent exchange for durable items not yet remembered and add 2-3.
8. Wrap-up pass: when the user says 收尾/结束/先这样, do a final pass (3-6 items).
   Skip banter, one-off commands and tool output in all three modes.
9. Session-start digest: if the workspace contains
   \`AI神经元记忆框架/scripts/session_digest.py\`, run
   \`<project>/.venv/Scripts/python.exe -m scripts.session_digest --recent 2\`
   from that project, review the JSON of recent user messages, and remember
   0-3 durable facts not already stored. Skip silently when the script or
   venv is absent.
`
}
