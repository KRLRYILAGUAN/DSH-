#!/usr/bin/env node
/**
 * One-time setup/check for dsh-plugin-neuron-memory.
 *
 * - Checks Node, Python, the neuron_memory package and the SQLite path.
 * - Creates the data directory.
 * - Prints the env vars the plugin/CLI read.
 */

import { existsSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { resolveConfig } from './cli.mjs'

const cfg = resolveConfig(process.env)
const home = cfg.pythonHome
const db = cfg.dbPath
const python = cfg.python

const checks = []
checks.push(['node', process.version])
checks.push(['python', existsSync(python) ? python : 'MISSING (set NEURON_PYTHON)'])
checks.push(['neuron_memory', existsSync(join(home, 'neuron_memory')) ? join(home, 'neuron_memory') : 'MISSING (set NEURON_HOME)'])
checks.push(['db', db])

if (existsSync(python)) {
  const r = spawnSync(python, ['-c', 'import sys; print(sys.version.split()[0])'], { encoding: 'utf8' })
  checks.push(['python version', (r.stdout || '').trim() || 'unknown'])
}

try {
  mkdirSync(join(db, '..'), { recursive: true })
} catch (err) {
  console.error(`cannot create db directory: ${err.message}`)
}

console.log('dsh-plugin-neuron-memory setup check')
for (const [k, v] of checks) console.log(`  ${k.padEnd(15)} ${v}`)
console.log('\nSet these before starting DSH (Windows PowerShell):')
console.log(`  $env:NEURON_HOME="${home}"`)
console.log(`  $env:NEURON_DB="${db}"`)
console.log(`  $env:NEURON_PYTHON="${python}"`)
