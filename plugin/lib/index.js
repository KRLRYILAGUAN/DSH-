/**
 * dsh-plugin-neuron-memory — Cordis plugin entry.
 *
 * Registers the `neuron-memory` skill and starts the read-only viewer as a
 * detached local service (:8420). The viewer is embedded by the Settings panel;
 * it must never keep DSH's event loop alive.
 */

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs'
import http from 'node:http'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { skillContent } from './skill.js'

export const name = 'neuron-memory'

export const inject = ['skills']

const BUNDLED_HOME = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'python')
const SESSIONS_DIR = join(homedir(), '.dsh', 'storages', 'session_projcache', 'sessions')

export const CONFIG_DEFAULTS = {
  enabled: true,
  registerSkill: true,
  pythonHome: '',
  dbPath: '',
}

/** Workspace directory of the current DSH session (from the session project cache). */
function sessionCwd() {
  const sid = process.env.DSH_SESSION_ID
  if (!sid) return ''
  try {
    const data = JSON.parse(readFileSync(join(SESSIONS_DIR, `${sid}.json`), 'utf8'))
    return data?.record?.identity?.cwd || ''
  } catch {
    return ''
  }
}

/** Fallback: the most recently touched session's workspace. */
function latestSessionCwd() {
  try {
    const files = readdirSync(SESSIONS_DIR)
      .filter((name) => name.endsWith('.json'))
      .map((name) => ({ name, mtime: statSync(join(SESSIONS_DIR, name)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, 8)
    for (const { name } of files) {
      try {
        const data = JSON.parse(readFileSync(join(SESSIONS_DIR, name), 'utf8'))
        const cwd = data?.record?.identity?.cwd
        if (cwd && existsSync(cwd)) return cwd
      } catch {
        // try the next session file
      }
    }
  } catch {
    // no cache
  }
  return ''
}

/** True only when the viewer answers and its database opens. */
function viewerUp(port) {
  return new Promise((resolvePromise) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/api/health', timeout: 800 }, (res) => {
      let body = ''
      res.on('data', (chunk) => { body += chunk })
      res.on('end', () => resolvePromise(res.statusCode === 200 && body.includes('"ok": true')))
    })
    req.on('error', () => resolvePromise(false))
    req.on('timeout', () => {
      req.destroy()
      resolvePromise(false)
    })
  })
}

/** Start the viewer detached; skip when a healthy one is already serving. */
async function ensureViewer(pythonHome, dbPath, port) {
  if (!pythonHome || !existsSync(join(pythonHome, 'viewer', 'server.py'))) return
  if (await viewerUp(port)) return
  const python = process.platform === 'win32'
    ? join(pythonHome, 'runtime', 'python.exe')
    : join(pythonHome, 'runtime', 'bin', 'python3')
  if (!existsSync(python)) return
  try {
    const child = spawn(
      python,
      ['-m', 'viewer.server', '--db', dbPath, '--port', String(port)],
      {
        cwd: pythonHome,
        env: { ...process.env, PYTHONPATH: pythonHome },
        detached: true,
        windowsHide: true,
        stdio: 'ignore',
      },
    )
    child.unref()
  } catch {
    // best effort: the panel still reports the health state
  }
}

export function apply(ctx, config = {}) {
  const merged = { ...CONFIG_DEFAULTS, ...config }

  if (!merged.enabled || !merged.registerSkill) {
    ctx.logger?.info('neuron-memory: disabled')
    return () => {}
  }

  const bundledHome = existsSync(join(BUNDLED_HOME, 'neuron_memory')) ? BUNDLED_HOME : ''
  const pythonHome = merged.pythonHome || process.env.NEURON_HOME || bundledHome
  const baseDir = sessionCwd() || latestSessionCwd() || process.cwd()
  const dbPath = merged.dbPath || process.env.NEURON_DB || join(baseDir, '.neuron-memory', 'neuron.db')
  try {
    mkdirSync(dirname(dbPath), { recursive: true })
  } catch {
    // best effort; the skill reports a clearer error later
  }

  if (!pythonHome) {
    ctx.logger?.warn('neuron-memory: no python home (set NEURON_HOME or ship the bundled runtime)')
  }

  if (!ctx.skills || typeof ctx.skills.register !== 'function') {
    ctx.logger?.warn('neuron-memory: skills service unavailable, skill not registered')
    return () => {}
  }

  const dispose = ctx.skills.register({
    name: 'neuron-memory',
    description: 'Neuron-style long-term memory: remember facts, recall by hybrid search, rehearse/forget, browse the graph.',
    whenToUse:
      'When the user shares a durable fact, preference, decision or project detail; when a question may depend on earlier context; when the user asks what you remember or asks you to forget.',
    content: skillContent({ pythonHome, dbPath }),
    source: 'dsh-plugin-neuron-memory',
  })

  ctx.logger?.info('neuron-memory: skill registered')
  void ensureViewer(pythonHome, dbPath, Number(process.env.NEURON_VIEWER_PORT || 8420))
  return () => {
    if (typeof dispose === 'function') dispose()
  }
}
