/**
 * dsh-plugin-neuron-memory — client half.
 *
 * Settings section 神经元记忆框架（实验）: the host starts the viewer (:8420)
 * detached; this panel embeds it on demand. Collapse lives on the right edge
 * of the board so it stays out of the way by default.
 */

window.__ModuleLoader__.load({
  id: 'dsh-plugin-neuron-memory',
  factory: (require) => {
    const React = require('react')
    const { useEffect, useState } = React
    const module = { exports: {} }
    const exports = module.exports

    const VIEWER_URL = 'http://127.0.0.1:8420/'
    const HEALTH_URL = 'http://127.0.0.1:8420/api/health'

    function HeaderButton() {
      return React.createElement(
        'button',
        {
          type: 'button',
          title: '打开神经元记忆看板',
          onClick: () => window.open(VIEWER_URL, '_blank', 'noopener,noreferrer'),
          style: {
            fontSize: 12, padding: '3px 9px', borderRadius: 7, cursor: 'pointer',
            border: '1px solid var(--dsw-alias-border-secondary, rgba(120,160,220,0.35))',
            background: 'transparent', color: 'inherit', lineHeight: 1.4,
          },
        },
        '记忆',
      )
    }

    function Section() {
      const [health, setHealth] = useState({ state: 'checking', notes: 0 })

      useEffect(() => {
        let alive = true
        let tries = 0
        const check = async () => {
          tries += 1
          try {
            const res = await fetch(HEALTH_URL, { cache: 'no-store' })
            const data = await res.json()
            if (!alive) return
            if (data?.ok) {
              setHealth({ state: 'up', notes: data.notes || 0 })
              return
            }
          } catch {
            // not up yet
          }
          if (!alive) return
          if (tries < 8) {
            setHealth({ state: 'starting', notes: 0 })
            setTimeout(check, 1500)
          } else {
            setHealth({ state: 'down', notes: 0 })
          }
        }
        check()
        return () => { alive = false }
      }, [])

      const box = {
        border: '1px solid var(--dsw-alias-border-secondary, rgba(120,160,220,0.25))',
        borderRadius: 10,
        overflow: 'hidden',
        background: 'var(--dsw-alias-bg-secondary, rgba(10,22,38,0.6))',
      }
      const head = {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 12px', gap: 12,
      }
      const title = { fontSize: 14, fontWeight: 600, margin: 0 }
      const text = { fontSize: 12, opacity: 0.75, margin: 0 }
      const dot = {
        display: 'inline-block', width: 8, height: 8, borderRadius: 4, marginRight: 6,
        background: health.state === 'up' ? '#4dd0a0' : (health.state === 'down' ? '#ff6b6b' : '#ffd166'),
      }
      const link = { fontSize: 12, color: '#7fc0ff', textDecoration: 'none' }
      const status = health.state === 'up'
        ? `看板运行中 · ${health.notes} 条记忆`
        : health.state === 'starting'
          ? '正在启动看板…'
          : '看板未运行：确认插件已启用'

      return React.createElement(
        'div',
        { style: { padding: '4px 0' } },
        React.createElement('div', { style: box },
          React.createElement('div', { style: head },
            React.createElement('div', null,
              React.createElement('h3', { style: title }, '神经元记忆框架（实验）'),
              React.createElement('p', { style: text },
                React.createElement('span', { style: dot }), status,
              ),
            ),
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
              React.createElement('a', { href: VIEWER_URL, target: '_blank', rel: 'noreferrer', style: link },
                health.state === 'up' ? '打开看板 →' : '新标签打开 →',
              ),
            ),
          ),
        ),
      )
    }

    function apply(ctx) {
      ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({
        name: 'conversation.session.header.actions',
        id: 'neuron-memory',
        order: 90,
      }, HeaderButton))
      ctx.slots.inject('settings.section', () => ctx.slots.register({
        name: 'settings.section',
        id: 'neuron-memory',
        order: 101,
        label: () => '神经元记忆框架（实验）',
      }, Section))
    }

    exports.apply = apply
    exports.inject = ['slots']
    return module.exports
  },
})
