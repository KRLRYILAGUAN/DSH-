import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

import { buildPythonArgs, resolveConfig } from '../scripts/cli.mjs'

test('resolveConfig honors env overrides', () => {
  const cfg = resolveConfig({
    NEURON_HOME: 'D:/memhome',
    NEURON_DB: 'D:/memhome/db.sqlite',
    NEURON_PYTHON: 'D:/python.exe',
  })
  assert.equal(cfg.pythonHome, resolve('D:/memhome'))
  assert.equal(cfg.dbPath, resolve('D:/memhome/db.sqlite'))
  assert.equal(cfg.python, 'D:/python.exe')
})

test('resolveConfig derives the venv interpreter from NEURON_HOME', () => {
  const cfg = resolveConfig({ NEURON_HOME: 'D:/memhome' })
  assert.ok(cfg.python.endsWith('python.exe') || cfg.python.endsWith('python') || cfg.python === 'python' || cfg.python === 'python3')
})

test('buildPythonArgs puts -m/--db before the command', () => {
  const args = buildPythonArgs('D:/db.sqlite', ['recall', 'q', '-k', '2'])
  assert.deepEqual(args, ['-m', 'neuron_memory', '--db', 'D:/db.sqlite', 'recall', 'q', '-k', '2'])
})

test('buildPythonArgs keeps command args intact', () => {
  const args = buildPythonArgs('/tmp/x.db', ['remember', '用户喜欢米饭', '--type', 'preference'])
  assert.equal(args.at(-1), 'preference')
  assert.ok(args.includes('用户喜欢米饭'))
})

test('package.json and cordis patch exist', () => {
  assert.ok(existsSync(new URL('../package.json', import.meta.url)))
  assert.ok(existsSync(new URL('../cordis.patch.yml', import.meta.url)))
})
