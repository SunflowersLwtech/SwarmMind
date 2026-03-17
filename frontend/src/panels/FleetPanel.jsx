import useMissionStore from '../stores/missionStore'

const STATUS_COLORS = {
  idle: '#06D6A0',
  moving: '#00D4FF',
  scanning: '#4DA8DA',
  returning: '#F4A261',
  charging: '#FFD166',
  offline: '#6C757D',
}

function PowerBar({ power }) {
  const color = power <= 20 ? '#E63946' : power <= 40 ? '#F4A261' : '#06D6A0'
  return (
    <div className="w-full h-1.5 rounded-full" style={{ background: '#1E3A5F' }}>
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${power}%`, background: color }}
      />
    </div>
  )
}

function UAVCard({ uav }) {
  const statusColor = STATUS_COLORS[uav.status] || '#6C757D'

  return (
    <div className="p-2.5 mb-1.5 rounded" style={{ background: '#0B1426', border: '1px solid #1E3A5F' }}>
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ background: statusColor }}
          />
          <span className="font-mono text-xs font-semibold" style={{ color: '#00D4FF' }}>
            {uav.id}
          </span>
        </div>
        <span className="font-mono text-xs uppercase" style={{ color: statusColor }}>
          {uav.status}
        </span>
      </div>

      <div className="flex items-center justify-between mb-1 font-mono text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
        <span>PWR {Math.round(uav.power)}%</span>
        <span>({uav.x},{uav.y})</span>
      </div>
      <PowerBar power={uav.power} />

      {uav.sector_id && (
        <div className="mt-1 font-mono text-xs" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Sector: {uav.sector_id}
        </div>
      )}
    </div>
  )
}

export default function FleetPanel() {
  const fleet = useMissionStore(s => s.fleet)

  return (
    <div className="h-full overflow-y-auto" style={{ background: '#111B2E' }}>
      <div className="panel-header">Fleet Status</div>
      <div className="p-2">
        {fleet.map(uav => (
          <UAVCard key={uav.id} uav={uav} />
        ))}
        {fleet.length === 0 && (
          <div className="text-center py-4 font-mono text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
            No UAVs deployed
          </div>
        )}
      </div>
    </div>
  )
}
