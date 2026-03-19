import useMissionStore from '../stores/missionStore'

function classifyEvent(evt) {
  const lower = evt.toLowerCase()
  if (lower.includes('found') || lower.includes('objective')) return { color: '#06D6A0', bg: 'rgba(6,214,160,0.1)' }
  if (lower.includes('safety') || lower.includes('critical')) return { color: '#E63946', bg: 'rgba(230,57,70,0.1)' }
  if (lower.includes('returning') || lower.includes('low') || lower.includes('power')) return { color: '#F4A261', bg: 'rgba(244,162,97,0.1)' }
  if (lower.includes('arrived') || lower.includes('waypoint')) return { color: '#4DA8DA', bg: 'rgba(77,168,218,0.1)' }
  if (lower.includes('charged') || lower.includes('fully')) return { color: '#FFD166', bg: 'rgba(255,209,102,0.1)' }
  if (lower.includes('complete') || lower.includes('mission')) return { color: '#00D4FF', bg: 'rgba(0,212,255,0.15)' }
  return { color: 'rgba(255,255,255,0.5)', bg: 'rgba(0,212,255,0.05)' }
}

export default function EventTimeline() {
  const events = useMissionStore(s => s.events)
  const tick = useMissionStore(s => s.tick)
  const missionStatus = useMissionStore(s => s.missionStatus)

  const recent = events.slice(-40)

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 border-t"
      style={{ background: '#111B2E', borderColor: '#1E3A5F' }}>
      <span className="font-mono text-[10px] shrink-0 tracking-wider" style={{ color: '#4DA8DA' }}>
        EVENTS
      </span>

      <div className="flex-1 flex items-center gap-1.5 overflow-x-auto">
        {recent.length === 0 && (
          <span className="font-mono text-[10px]" style={{ color: 'rgba(255,255,255,0.2)' }}>
            {missionStatus === 'idle' ? 'Press START to begin search and rescue mission' : 'No events yet'}
          </span>
        )}
        {recent.map((evt, i) => {
          const style = classifyEvent(evt)
          return (
            <span
              key={i}
              className="font-mono text-[10px] whitespace-nowrap px-2 py-0.5 rounded shrink-0"
              style={{
                background: style.bg,
                color: style.color,
                border: `1px solid ${style.color}30`,
              }}
            >
              {evt}
            </span>
          )
        })}
      </div>

      <span className="font-mono text-[10px] shrink-0 tabular-nums" style={{ color: 'rgba(255,255,255,0.3)' }}>
        T+{tick}
      </span>
    </div>
  )
}
