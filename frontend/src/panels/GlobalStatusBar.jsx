import useMissionStore from '../stores/missionStore'

function StatusDot({ status }) {
  const colors = {
    idle: 'bg-gray-500',
    running: 'bg-green-400 animate-pulse',
    paused: 'bg-yellow-400',
    completed: 'bg-emerald-400',
  }
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-gray-500'}`} />
}

export default function GlobalStatusBar() {
  const missionStatus = useMissionStore(s => s.missionStatus)
  const tick = useMissionStore(s => s.tick)
  const fleet = useMissionStore(s => s.fleet)
  const coverage = useMissionStore(s => s.coverage)
  const objectivesFound = useMissionStore(s => s.objectivesFound)
  const objectivesTotal = useMissionStore(s => s.objectivesTotal)
  const connected = useMissionStore(s => s.connected)

  const activeCount = fleet.filter(u => u.status !== 'offline').length

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b"
      style={{ background: '#111B2E', borderColor: '#1E3A5F' }}>

      <div className="flex items-center gap-3">
        <span className="font-mono text-sm font-bold" style={{ color: '#00D4FF' }}>
          SWARMMIND
        </span>
        <span className="text-xs" style={{ color: 'rgba(255,255,255,0.4)' }}>|</span>
        <span className="font-mono text-xs" style={{ color: '#4DA8DA' }}>
          OP: TYPHOON RESCUE
        </span>
      </div>

      <div className="flex items-center gap-6 font-mono text-xs">
        <div className="flex items-center gap-2">
          <StatusDot status={missionStatus} />
          <span className="uppercase" style={{ color: 'rgba(255,255,255,0.6)' }}>
            {missionStatus}
          </span>
        </div>

        <div style={{ color: 'rgba(255,255,255,0.6)' }}>
          T+{String(Math.floor(tick / 60)).padStart(2, '0')}:{String(tick % 60).padStart(2, '0')}
        </div>

        <div style={{ color: '#06D6A0' }}>
          {activeCount}/{fleet.length} UAV
        </div>

        <div style={{ color: '#00D4FF' }}>
          {coverage.toFixed(1)}% COV
        </div>

        <div style={{ color: '#F4A261' }}>
          {objectivesFound}/{objectivesTotal} OBJ
        </div>

        <div className="flex items-center gap-1">
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${connected ? 'bg-green-400' : 'bg-red-500 animate-pulse'}`} />
          <span style={{ color: 'rgba(255,255,255,0.4)' }}>
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>
    </div>
  )
}
