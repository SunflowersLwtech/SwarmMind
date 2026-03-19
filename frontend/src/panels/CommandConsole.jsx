import { useRef, useEffect, useMemo, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import useMissionStore from '../stores/missionStore'
import useWebSocket from '../hooks/useWebSocket'

function sendOpsCommand(sendWs, type) {
  if (!sendWs(type)) {
    const ep = { start: 'start', pause: 'pause', resume: 'resume', stop: 'stop', reset: 'reset' }[type]
    if (ep) fetch(`/api/ops/${ep}`, { method: 'POST' }).catch(console.error)
  }
}

/* ── Pipeline stage metadata ─────────────────────────────── */

const STAGES = {
  assessor:   { step: 1, label: 'ASSESS',   verb: 'Reading situation',   color: '#4DA8DA', icon: '1' },
  strategist: { step: 2, label: 'PLAN',     verb: 'Deciding strategy',   color: '#06D6A0', icon: '2' },
  dispatcher: { step: 3, label: 'EXECUTE',  verb: 'Sending MCP commands',color: '#F4A261', icon: '3' },
  analyst:    { step: 4, label: 'REPORT',   verb: 'Summarizing results', color: '#00D4FF', icon: '4' },
}

const MCP_TOOL_DESCRIPTIONS = {
  discover_fleet:             'Read all drone status & missions',
  get_drone_status:           'Read single drone telemetry',
  assign_search_mission:      'COMMAND: Send drone to target',
  assign_scan_mission:        'COMMAND: Thermal scan at position',
  recall_drone:               'COMMAND: Return drone to base',
  get_situation_overview:      'Read full situation (composite)',
  get_frontier_targets:        'Read unexplored frontiers',
  plan_route:                 'Evaluate A* route cost',
}

/* ── Markdown theme ──────────────────────────────────────── */

const md = {
  p: ({ children }) => <p className="my-1 leading-relaxed break-words whitespace-pre-wrap">{children}</p>,
  strong: ({ children }) => <strong style={{ color: '#fff' }}>{children}</strong>,
  code: ({ children, className }) => {
    if (className?.startsWith('language-'))
      return <code className="block my-1.5 p-2 rounded text-[11px] font-mono whitespace-pre-wrap break-all min-w-0" style={{ background: 'rgba(0,0,0,0.35)', color: '#06D6A0' }}>{children}</code>
    return <code className="px-1 py-0.5 rounded text-[11px] font-mono break-all whitespace-pre-wrap" style={{ background: 'rgba(0,0,0,0.3)', color: '#F4A261' }}>{children}</code>
  },
  ul: ({ children }) => <ul className="ml-4 my-1 list-disc">{children}</ul>,
  ol: ({ children }) => <ol className="ml-4 my-1 list-decimal">{children}</ol>,
  li: ({ children }) => <li className="my-0.5 leading-relaxed break-words">{children}</li>,
}

function compactJson(obj) {
  return JSON.stringify(obj, null, 2).replace(
    /\[([^\[\]]{0,60})\]/g,
    m => { const c = m.replace(/\s*\n\s*/g, ' '); return c.length <= 80 ? c : m }
  )
}
function tryJson(s) {
  try { return JSON.parse(s) } catch { try { return JSON.parse(s.replace(/'/g, '"')) } catch { return null } }
}

function classifyEvent(evt) {
  const lower = evt.toLowerCase()
  if (lower.includes('found') || lower.includes('objective')) return { color: '#06D6A0', bg: 'rgba(6,214,160,0.1)' }
  if (lower.includes('safety') || lower.includes('critical')) return { color: '#E63946', bg: 'rgba(230,57,70,0.1)' }
  if (lower.includes('returning') || lower.includes('low') || lower.includes('power')) return { color: '#F4A261', bg: 'rgba(244,162,97,0.1)' }
  if (lower.includes('arrived') || lower.includes('waypoint')) return { color: '#4DA8DA', bg: 'rgba(77,168,218,0.1)' }
  if (lower.includes('charged') || lower.includes('fully')) return { color: '#FFD166', bg: 'rgba(255,209,102,0.1)' }
  if (lower.includes('complete') || lower.includes('mission')) return { color: '#00D4FF', bg: 'rgba(0,212,255,0.15)' }
  return { color: 'rgba(255,255,255,0.5)', bg: 'rgba(255,255,255,0.05)' }
}

/* ── Collapsible blocks ──────────────────────────────────── */

function Code({ text, color }) {
  const [open, setOpen] = useState(false)
  const isMultiline = text.includes('\n') || text.length > 60

  if (!isMultiline) {
    return (
      <code className="block px-1.5 py-1 mt-0.5 rounded text-[10px] font-mono whitespace-pre-wrap break-all min-w-0"
        style={{ background: 'rgba(0,0,0,0.2)', color: color || 'rgba(255,255,255,0.5)' }}>
        {text}
      </code>
    )
  }

  const peek = text.replace(/\s+/g, ' ').slice(0, 80) + (text.length > 80 ? '...' : '')
  return (
    <div className="mt-0.5 min-w-0 w-full">
      <div 
        onClick={() => setOpen(!open)}
        className="cursor-pointer flex items-start gap-1 p-1 rounded hover:bg-white/5 transition-colors"
        style={{ background: 'rgba(0,0,0,0.2)' }}
      >
        <span className="shrink-0 text-[9px] opacity-40 select-none mt-0.5">{open ? '▼' : '▶'}</span>
        <code className="text-[10px] font-mono leading-relaxed whitespace-pre-wrap break-all min-w-0"
          style={{ color: color || 'rgba(255,255,255,0.5)' }}>
          {open ? text : peek}
        </code>
      </div>
    </div>
  )
}

function ReasoningBlock({ text }) {
  const [open, setOpen] = useState(false)
  const isLong = text.includes('\n') || text.length > 80

  if (!isLong) {
    return (
      <div className="mt-0.5 pl-2.5 font-sans text-[11.5px] tracking-wide leading-relaxed" style={{ color: 'rgba(255,255,255,0.9)', borderLeft: '2px solid rgba(77,168,218,0.2)' }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{text}</ReactMarkdown>
      </div>
    )
  }

  if (open) {
    return (
      <div className="mt-0.5 min-w-0 w-full">
        <div onClick={() => setOpen(false)} className="cursor-pointer flex items-center gap-1 py-0.5 hover:opacity-80 w-fit" style={{ color: '#4DA8DA' }}>
          <span className="text-[9px]">▼</span>
          <span className="text-[10px] font-mono font-bold">REASONING</span>
        </div>
        <div className="pl-2.5 font-sans text-[11.5px] tracking-wide leading-relaxed" style={{ color: 'rgba(255,255,255,0.9)', borderLeft: '2px solid rgba(77,168,218,0.2)' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>{text}</ReactMarkdown>
        </div>
      </div>
    )
  }

  const peek = text.replace(/\s+/g, ' ').slice(0, 80) + '...'
  return (
    <div className="mt-0.5 min-w-0 w-full">
      <div onClick={() => setOpen(true)} className="cursor-pointer flex items-start gap-1 py-0.5 hover:opacity-80" style={{ color: 'rgba(255,255,255,0.6)' }}>
        <span className="shrink-0 text-[9px] mt-0.5" style={{ color: '#4DA8DA' }}>▶</span>
        <span className="font-sans text-[11px] truncate">{peek}</span>
      </div>
    </div>
  )
}

/* ── Pipeline stage banner ───────────────────────────────── */

function StageBanner({ agent }) {
  const s = STAGES[agent]
  if (!s) return null
  return (
    <div className="flex items-center gap-2 mt-2 mb-0.5 px-2 py-0.5 rounded"
      style={{ background: `linear-gradient(90deg, ${s.color}15, transparent)`, borderLeft: `2px solid ${s.color}` }}>
      <span className="text-[9px] font-mono font-bold" style={{ color: s.color }}>[{s.step}/4] {s.label}</span>
      <span className="text-[9px] font-sans opacity-60" style={{ color: 'white' }}>{s.verb}</span>
    </div>
  )
}

/* ── Single log entry ────────────────────────────────────── */

function LogEntry({ log }) {
  const content = useMemo(() => {
    if (log.action === 'reasoning') {
      return <ReasoningBlock text={log.detail} />
    }

    if (log.action === 'tool_call') {
      const match = log.detail.match(/^(\w+)\((.+)\)$/s)
      if (!match) return <span style={{ color: 'rgba(255,255,255,0.7)' }}>{log.detail}</span>
      const [, fn, argsRaw] = match
      const parsed = tryJson(argsRaw)
      const desc = MCP_TOOL_DESCRIPTIONS[fn]
      const isCommand = desc?.startsWith('COMMAND')
      return (
        <div className="mt-0.5 pl-2.5 py-1 rounded min-w-0 w-full" style={{ borderLeft: `2px solid ${isCommand ? '#F4A261' : '#4DA8DA'}` }}>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[9px] font-mono font-bold tracking-wider"
              style={{ color: isCommand ? '#F4A261' : '#4DA8DA' }}>
              {isCommand ? 'EXEC' : 'CALL'}
            </span>
            <span className="font-mono text-[11px] font-semibold break-all" style={{ color: 'rgba(255,255,255,0.9)' }}>{fn}()</span>
            {desc && <span className="text-[10px] font-sans ml-0.5" style={{ color: 'rgba(255,255,255,0.4)' }}>{desc.replace('COMMAND: ', '')}</span>}
          </div>
          {parsed && Object.keys(parsed).length > 0 && <Code text={compactJson(parsed)} />}
        </div>
      )
    }

    if (log.action === 'tool_result') {
      const idx = log.detail.indexOf(' \u2192 ')
      if (idx === -1) return <span style={{ color: 'rgba(255,255,255,0.7)' }}>{log.detail}</span>
      const fn = log.detail.slice(0, idx)
      const raw = log.detail.slice(idx + 3)
      const parsed = tryJson(raw)
      return (
        <div className="mt-0.5 pl-2.5 min-w-0 w-full" style={{ borderLeft: '2px solid rgba(6,214,160,0.3)' }}>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] font-mono font-bold tracking-wider" style={{ color: '#06D6A0' }}>RES</span>
            <span className="text-[10px] font-mono" style={{ color: 'rgba(255,255,255,0.4)' }}>{fn}</span>
          </div>
          {parsed ? <Code text={compactJson(parsed)} color="#06D6A0" /> :
            <Code text={raw} color="rgba(255,255,255,0.4)" />}
        </div>
      )
    }

    if (log.action === 'system_event') {
      const style = classifyEvent(log.detail)
      return (
        <div className="mt-0.5 px-2 py-1 rounded min-w-0 w-full flex items-start gap-1.5" style={{ background: style.bg, border: `1px solid ${style.color}30` }}>
          <span className="text-[9px] font-mono font-bold tracking-wider mt-[1px]" style={{ color: style.color }}>SYS</span>
          <span className="font-mono text-[10.5px] whitespace-pre-wrap break-words" style={{ color: style.color }}>{log.detail}</span>
        </div>
      )
    }

    return <span className="font-sans text-[11px] leading-relaxed" style={{ color: 'rgba(255,255,255,0.85)' }}>{log.detail}</span>
  }, [log.action, log.detail])

  return (
    <div className="log-entry py-1.5 border-b" style={{ borderColor: 'rgba(255,255,255,0.03)' }}>
      {content}
    </div>
  )
}

/* ── Filter tabs ─────────────────────────────────────────── */

const FILTERS = [
  { key: 'all',          label: 'All' },
  { key: 'system_event', label: 'Events' },
  { key: 'reasoning',    label: 'Thinking' },
  { key: 'tool_call',    label: 'MCP Calls' },
  { key: 'tool_result',  label: 'Results' },
]

/* ── Main component ──────────────────────────────────────── */

export default function CommandConsole() {
  const events = useMissionStore(s => s.events)
  const agentLogs = useMissionStore(s => s.agentLogs)
  const agentStatus = useMissionStore(s => s.agentStatus)
  const agentCycle = useMissionStore(s => s.agentCycle)
  const missionStatus = useMissionStore(s => s.missionStatus)
  const logRef = useRef(null)
  const { sendCommand } = useWebSocket()
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [events, agentLogs])

  const filtered = filter === 'all' ? agentLogs : agentLogs.filter(l => l.action === filter)

  // Count MCP calls for stats
  const mcpCalls = agentLogs.filter(l => l.action === 'tool_call').length
  const mcpWrites = agentLogs.filter(l => l.action === 'tool_call' && MCP_TOOL_DESCRIPTIONS[l.detail?.match(/^(\w+)\(/)?.[1]]?.startsWith('COMMAND')).length

  // Build entries with stage banners
  let lastAgent = null
  const entries = []
  for (const log of filtered) {
    if (log.agent !== 'SYS' && log.agent !== lastAgent) {
      entries.push({ type: 'stage', agent: log.agent, key: `stage-${entries.length}` })
      lastAgent = log.agent
    }
    entries.push({ type: 'log', log, key: `log-${entries.length}` })
  }

  return (
    <div className="h-full flex flex-col" style={{ background: '#111B2E' }}>
      {/* Header */}
      <div className="panel-header flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>AI Decision Log</span>
          {agentStatus === 'thinking' && (
            <span className="flex items-center gap-1 text-[10px]" style={{ color: '#4DA8DA' }}>
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              cycle #{agentCycle}
            </span>
          )}
          {agentStatus === 'error' && (
            <span className="text-[10px] px-1 rounded" style={{ color: '#E63946', background: 'rgba(230,57,70,0.1)' }}>ERROR</span>
          )}
        </div>
        {mcpCalls > 0 && (
          <span className="text-[10px] font-mono" style={{ color: 'rgba(255,255,255,0.25)' }}>
            {mcpCalls} calls / {mcpWrites} commands
          </span>
        )}
      </div>

      {/* Filter bar */}
      {agentLogs.length > 0 && (
        <div className="flex gap-0.5 px-2 py-1 border-b" style={{ borderColor: 'rgba(30,58,95,0.3)' }}>
          {FILTERS.map(f => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className="px-1.5 py-0.5 rounded text-[10px] font-mono"
              style={{
                background: filter === f.key ? 'rgba(77,168,218,0.2)' : 'transparent',
                color: filter === f.key ? '#4DA8DA' : 'rgba(255,255,255,0.3)',
              }}>{f.label}</button>
          ))}
          <span className="ml-auto text-[10px] font-mono tabular-nums" style={{ color: 'rgba(255,255,255,0.2)' }}>
            {filtered.length}
          </span>
        </div>
      )}

      {/* Log area */}
      <div ref={logRef} className="flex-1 overflow-y-auto overflow-x-hidden p-2 font-mono text-xs w-full min-w-0 break-words" style={{ color: 'rgba(255,255,255,0.7)' }}>

        {agentLogs.length === 0 && (
          <div className="text-center py-8" style={{ color: 'rgba(255,255,255,0.2)' }}>
            <div className="text-sm mb-2">SwarmMind SAR</div>
            <div className="text-[10px] leading-relaxed mb-4">
              AI agent uses a 4-stage pipeline each cycle:<br />
              <span style={{ color: '#4DA8DA' }}>1 Assess</span> {'\u2192 '}
              <span style={{ color: '#06D6A0' }}>2 Plan</span> {'\u2192 '}
              <span style={{ color: '#F4A261' }}>3 Execute</span> {'\u2192 '}
              <span style={{ color: '#00D4FF' }}>4 Report</span>
            </div>
            <div className="text-[10px]" style={{ color: 'rgba(255,255,255,0.15)' }}>
              System events and MCP tool calls will appear here in real-time
            </div>
          </div>
        )}

        {/* Agent pipeline log */}
        {entries.map(e =>
          e.type === 'stage'
            ? <StageBanner key={e.key} agent={e.agent} />
            : <LogEntry key={e.key} log={e.log} />
        )}
      </div>

      {/* Controls */}
      <div className="p-2 border-t flex gap-1.5" style={{ borderColor: '#1E3A5F' }}>
        {missionStatus === 'idle' && (
          <button onClick={() => sendOpsCommand(sendCommand, 'start')}
            className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
            style={{ background: '#06D6A0', color: '#0B1426' }}>START MISSION</button>
        )}
        {missionStatus === 'running' && (
          <button onClick={() => sendOpsCommand(sendCommand, 'pause')}
            className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
            style={{ background: '#F4A261', color: '#0B1426' }}>PAUSE</button>
        )}
        {missionStatus === 'paused' && (
          <>
            <button onClick={() => sendOpsCommand(sendCommand, 'resume')}
              className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
              style={{ background: '#06D6A0', color: '#0B1426' }}>RESUME</button>
            <button onClick={() => sendOpsCommand(sendCommand, 'stop')}
              className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
              style={{ background: '#E63946', color: 'white' }}>STOP</button>
          </>
        )}
        {missionStatus === 'completed' && (
          <div className="flex-1 py-1.5 rounded font-mono text-xs font-semibold text-center"
            style={{ background: 'rgba(0,212,255,0.15)', color: '#00D4FF', border: '1px solid rgba(0,212,255,0.3)' }}>
            MISSION COMPLETE</div>
        )}
        <button onClick={() => sendOpsCommand(sendCommand, 'reset')}
          className="px-3 py-1.5 rounded font-mono text-xs"
          style={{ background: '#1E3A5F', color: 'rgba(255,255,255,0.6)' }}>RESET</button>
      </div>
    </div>
  )
}
