import test from 'node:test'
import assert from 'node:assert/strict'

import { apply } from '../lib/index.js'
import { skillContent } from '../lib/skill.js'

function fakeCtx() {
  const registered = []
  const logs = []
  return {
    registered,
    logs,
    skills: {
      register(skill) {
        registered.push(skill)
        return () => {}
      },
    },
    logger: {
      info: (m) => logs.push(['info', m]),
      warn: (m) => logs.push(['warn', m]),
    },
  }
}

test('apply registers the neuron-memory skill with resolved paths', () => {
  const ctx = fakeCtx()
  const dispose = apply(ctx, { pythonHome: 'D:/mem', dbPath: 'D:/mem/neuron.db' })

  assert.equal(ctx.registered.length, 1)
  const skill = ctx.registered[0]
  assert.equal(skill.name, 'neuron-memory')
  assert.match(skill.content, /D:\/mem/)
  assert.match(skill.content, /remember/)
  assert.match(skill.content, /recall/)
  assert.equal(typeof dispose, 'function')
  dispose()
})

test('apply is a no-op when disabled', () => {
  const ctx = fakeCtx()
  apply(ctx, { enabled: false })
  assert.equal(ctx.registered.length, 0)
})

test('apply warns and skips when the skills service is missing', () => {
  const logs = []
  const ctx = { logger: { info: () => {}, warn: (m) => logs.push(m) } }
  const dispose = apply(ctx, { pythonHome: 'D:/mem' })
  assert.equal(typeof dispose, 'function')
  assert.ok(logs.some((m) => m.includes('skills service unavailable')))
})

test('apply resolves a python home from config, env or the bundled runtime', () => {
  const ctx = fakeCtx()
  const prev = process.env.NEURON_HOME
  delete process.env.NEURON_HOME
  try {
    apply(ctx, {})
  } finally {
    if (prev === undefined) delete process.env.NEURON_HOME
    else process.env.NEURON_HOME = prev
  }
  assert.equal(ctx.registered.length, 1)
  const content = ctx.registered[0].content
  if (content.includes('<NEURON_HOME>')) {
    assert.ok(ctx.logs.some(([level, m]) => level === 'warn' && m.includes('python home')))
  } else {
    assert.ok(content.includes('python'))
  }
})

test('skillContent carries the CLI protocol and paths', () => {
  const text = skillContent({ pythonHome: '/x/home', dbPath: '/x/db.sqlite' })
  for (const cmd of ['remember', 'recall', 'forget', 'stats', 'history', 'consolidate']) {
    assert.ok(text.includes(cmd), `missing ${cmd}`)
  }
  assert.ok(text.includes('/x/home'))
  assert.ok(text.includes('/x/db.sqlite'))
  assert.ok(text.includes('cli.mjs'))
  assert.ok(text.includes('127.0.0.1:8420'))
})
