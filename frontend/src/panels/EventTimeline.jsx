import useMissionStore from '../stores/missionStore'

export default function EventTimeline() {
  const events = useMissionStore(s => s.events)
  const tick = useMissionStore(s => s.tick)

  const recent = events.slice(-8)

  return (
    <div className="flex items-center gap-3 px-4 py-1.5 border-t overflow-hidden"
      style={{ background: '#111B2E', borderColor: '#1E3A5F' }}>
      <span className="font-mono text-xs shrink-0" style={{ color: '#4DA8DA' }}>
        TIMELINE
      </span>
      <div className="flex-1 flex items-center gap-2 overflow-x-auto">
        {recent.map((evt, i) => (
          <span
            key={i}
            className="font-mono text-xs whitespace-nowrap px-2 py-0.5 rounded"
            style={{
              background: 'rgba(0,212,255,0.08)',
              color: 'rgba(255,255,255,0.6)',
              border: '1px solid rgba(30,58,95,0.5)',
            }}
          >
            {evt}
          </span>
        ))}
        {recent.length === 0 && (
          <span className="font-mono text-xs" style={{ color: 'rgba(255,255,255,0.2)' }}>
            No events yet
          </span>
        )}
      </div>
      <span className="font-mono text-xs shrink-0" style={{ color: 'rgba(255,255,255,0.3)' }}>
        T+{tick}
      </span>
    </div>
  )
}
