import useMissionStore from '../stores/missionStore'

function Stat({ label, value, unit, color }) {
  return (
    <div className="p-2 rounded" style={{ background: '#0B1426', border: '1px solid #1E3A5F' }}>
      <div className="font-mono text-xs mb-0.5" style={{ color: 'rgba(255,255,255,0.4)' }}>
        {label}
      </div>
      <div className="font-mono text-lg font-bold" style={{ color }}>
        {value}<span className="text-xs ml-0.5" style={{ color: 'rgba(255,255,255,0.4)' }}>{unit}</span>
      </div>
    </div>
  )
}

export default function OpDashboard() {
  const coverage = useMissionStore(s => s.coverage)
  const fleet = useMissionStore(s => s.fleet)
  const objectivesFound = useMissionStore(s => s.objectivesFound)
  const objectivesTotal = useMissionStore(s => s.objectivesTotal)
  const tick = useMissionStore(s => s.tick)

  const avgPower = fleet.length > 0
    ? (fleet.reduce((sum, u) => sum + u.power, 0) / fleet.length).toFixed(0)
    : 0
  const activeCount = fleet.filter(u => u.status !== 'offline').length

  return (
    <div style={{ background: '#111B2E' }}>
      <div className="panel-header">Operations Dashboard</div>
      <div className="grid grid-cols-2 gap-1.5 p-2">
        <Stat label="COVERAGE" value={coverage.toFixed(1)} unit="%" color="#00D4FF" />
        <Stat label="OBJECTIVES" value={`${objectivesFound}/${objectivesTotal}`} unit="" color="#E63946" />
        <Stat label="ACTIVE UAV" value={`${activeCount}/${fleet.length}`} unit="" color="#06D6A0" />
        <Stat label="AVG POWER" value={avgPower} unit="%" color="#FFD166" />
      </div>

      {/* Coverage progress bar */}
      <div className="px-2 pb-2">
        <div className="w-full h-2 rounded-full" style={{ background: '#1E3A5F' }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(coverage, 100)}%`,
              background: 'linear-gradient(90deg, #00D4FF, #06D6A0)',
            }}
          />
        </div>
        <div className="flex justify-between mt-1 font-mono text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
          <span>0%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  )
}
