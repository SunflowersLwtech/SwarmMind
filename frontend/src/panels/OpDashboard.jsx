import useMissionStore from '../stores/missionStore'

function Stat({ label, value, unit, color, detail }) {
  return (
    <div className="p-2 rounded" style={{ background: '#0B1426', border: '1px solid #1E3A5F' }}>
      <div className="font-mono text-[10px] mb-0.5 tracking-wider" style={{ color: 'rgba(255,255,255,0.35)' }}>
        {label}
      </div>
      <div className="font-mono text-lg font-bold leading-none" style={{ color }}>
        {value}
        {unit && <span className="text-xs ml-0.5" style={{ color: 'rgba(255,255,255,0.35)' }}>{unit}</span>}
      </div>
      {detail && (
        <div className="font-mono text-[10px] mt-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
          {detail}
        </div>
      )}
    </div>
  )
}

export default function OpDashboard() {
  const coverage = useMissionStore(s => s.coverage)
  const fleet = useMissionStore(s => s.fleet)
  const objectives = useMissionStore(s => s.objectives)
  const objectivesFound = useMissionStore(s => s.objectivesFound)
  const objectivesTotal = useMissionStore(s => s.objectivesTotal)
  const agentCycle = useMissionStore(s => s.agentCycle)

  const avgPower = fleet.length > 0
    ? Math.round(fleet.reduce((sum, u) => sum + u.power, 0) / fleet.length)
    : 0
  const activeCount = fleet.filter(u => u.status !== 'offline').length
  const movingCount = fleet.filter(u => u.status === 'moving').length
  const scanningCount = fleet.filter(u => u.status === 'scanning').length
  const chargingCount = fleet.filter(u => u.status === 'charging').length

  // Derive found objectives from the objectives array if available
  const detected = objectives.filter(o => o.detected).length

  const fleetDetail = [
    movingCount && `${movingCount} flying`,
    scanningCount && `${scanningCount} scanning`,
    chargingCount && `${chargingCount} charging`,
  ].filter(Boolean).join(', ') || 'all idle'

  return (
    <div style={{ background: '#111B2E' }}>
      <div className="panel-header flex items-center justify-between">
        <span>Operations</span>
        {agentCycle > 0 && (
          <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.25)' }}>
            cycle #{agentCycle}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5 p-2">
        <Stat
          label="SEARCH COVERAGE"
          value={coverage.toFixed(1)}
          unit="%"
          color="#00D4FF"
          detail={`${Math.round(coverage * 4)}/${20*20} cells`}
        />
        <Stat
          label="SURVIVORS"
          value={`${objectivesFound}/${objectivesTotal}`}
          color={objectivesFound >= objectivesTotal && objectivesTotal > 0 ? '#06D6A0' : '#F4A261'}
          detail={objectivesFound >= objectivesTotal && objectivesTotal > 0 ? 'all found' : `${objectivesTotal - objectivesFound} remaining`}
        />
        <Stat
          label="FLEET"
          value={`${activeCount}/${fleet.length}`}
          color="#06D6A0"
          detail={fleetDetail}
        />
        <Stat
          label="AVG POWER"
          value={avgPower}
          unit="%"
          color={avgPower <= 20 ? '#E63946' : avgPower <= 40 ? '#F4A261' : '#FFD166'}
          detail={avgPower <= 20 ? 'critical' : avgPower <= 40 ? 'low' : 'nominal'}
        />
      </div>

      {/* Coverage bar */}
      <div className="px-2 pb-2">
        <div className="w-full h-1.5 rounded-full" style={{ background: '#1E3A5F' }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(coverage, 100)}%`,
              background: coverage >= 80 ? '#06D6A0' : 'linear-gradient(90deg, #00D4FF, #06D6A0)',
            }}
          />
        </div>
      </div>
    </div>
  )
}
