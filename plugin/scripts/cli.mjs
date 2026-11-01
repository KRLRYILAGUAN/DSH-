#!/usr/bin/env node
/**
 * CLI bridge: dsh-neuron-memory <command> [...args]
 *
 * Spawns `python -m neuron_memory --db <db> <command>` from the Python home.
 * Resolution order:
 *   python  : NEURON_PYTHON > <home>/.venv/(Scripts|bin)/python > python3/python
 *   home    : NEURON_HOME > cwd
 *   db      : NEURON_DB > ~/.neuron-memory/neuron.db
 */

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BUNDLED_HOME = join(PLUGIN_ROOT, 'python')
const BUNDLED_PYTHON = join(
  BUNDLED_HOME,
  'runtime',
  process.platform === 'win32' ? 'python.exe' : 'bin/python3',
)

const HELP = `dsh-neuron-memory — CLI bridge to the neuron_memory Python core

Usage:
  dsh-neuron-memory remember "<fact>" [--type fact] [--importance 0.8]
  dsh-neuron-memory recall "<query>" [-k 5] [--as-of ISO_TIME]
  dsh-neuron-memory mention <id> [--source user|self|consolidate|implicit]
  dsh-neuron-memory rehearse <id>
  dsh-neuron-memory forget <id>
  dsh-neuron-memory restore <id>
  dsh-neuron-memory history <id>
  dsh-neuron-memory stats
  dsh-neuron-memory bridge --dir ~/.memory
  dsh-neuron-memory consolidate
  dsh-neuron-memory demo

Env:
  NEURON_HOME     directory containing the neuron_memory package (default: cwd)
  NEURON_PYTHON   python executable (default: <home>/.venv or python3)
  NEURON_DB       sqlite path (default: ~/.neuron-memory/neuron.db)
`

/** Resolve python home, db path and interpreter from an env object. */
export function resolveConfig(env = process.env) {
  const hasBundled = existsSync(join(BUNDLED_HOME, 'neuron_memory'))
  const pythonHome = resolve(env.NEURON_HOME || (hasBundled ? BUNDLED_HOME : process.cwd()))
  const dbPath = resolve(env.NEURON_DB || join(process.cwd(), '.neuron-memory', 'neuron.db'))
  const venvPython =
    process.platform === 'win32'
      ? join(pythonHome, '.venv', 'Scripts', 'python.exe')
      : join(pythonHome, '.venv', 'bin', 'python')

  let python = env.NEURON_PYTHON
  if (!python) {
    if (existsSync(venvPython)) python = venvPython
    else if (existsSync(BUNDLED_PYTHON)) python = BUNDLED_PYTHON
    else python = process.platform === 'win32' ? 'python' : 'python3'
  }
  return { pythonHome, dbPath, python, venvPython, hasBundled }
}

/** Build the python argv for a neuron_memory command. */
export function buildPythonArgs(dbPath, args = []) {
  return ['-m', 'neuron_memory', '--db', dbPath, ...args]
}

export function main(argv = process.argv.slice(2)) {
  if (argv.includes('--help') || argv.includes('-h') || argv.length === 0) {
    console.log(HELP)
    return
  }

  const { pythonHome, python } = resolveConfig()
  let { dbPath } = resolveConfig()

  if (python.includes('\\') || python.includes('/')) {
    if (!existsSync(python)) {
      console.error(`dsh-neuron-memory: python not found at ${python}\nSet NEURON_PYTHON or install Python 3.10+.`)
      process.exitCode = 127
      return
    }
  }

  try {
    mkdirSync(dirname(dbPath), { recursive: true })
  } catch (err) {
    const fallback = resolve(process.cwd(), '.neuron-memory', 'neuron.db')
    try {
      mkdirSync(dirname(fallback), { recursive: true })
      console.error(`dsh-neuron-memory: ${dbPath} not writable (${err.code || err.message}); using ${fallback}`)
      dbPath = fallback
    } catch (err2) {
      console.error(`dsh-neuron-memory: cannot create db directory for ${dbPath}: ${err.message}`)
    }
  }

  const sep = process.platform === 'win32' ? ';' : ':'
  const env = {
    ...process.env,
    PYTHONPATH: [pythonHome, process.env.PYTHONPATH].filter(Boolean).join(sep),
  }

  // Let the host plugin (viewer auto-start) follow the same database the CLI used.
  try {
    writeFileSync(join(tmpdir(), 'neuron-memory-db.txt'), `${dbPath}\n`)
  } catch {
    // non-fatal: the viewer falls back to its configured/default path
  }

  const child = spawn(python, buildPythonArgs(dbPath, argv), {
    cwd: pythonHome,
    stdio: 'inherit',
    env,
  })

  child.on('error', (err) => {
    console.error(`dsh-neuron-memory: failed to start python (${python}): ${err.message}`)
    process.exitCode = 127
  })

  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal)
    else if (code === 9009 || code === 127) {
      console.error(
        'dsh-neuron-memory: python could not be started (Windows Store stub or missing Python).\n' +
        `  NEURON_HOME=${pythonHome}\n  Set NEURON_PYTHON to a real python.exe, or install Python 3.10+.`
      )
      process.exitCode = 127
    } else {
      process.exitCode = code ?? 1
    }
  })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main()
}
