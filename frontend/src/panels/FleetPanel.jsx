import { useState } from 'react'
import useMissionStore from '../stores/missionStore'
import { sendCommand } from '../hooks/useWebSocket'

const STATUS_COLORS = {
  idle: '#06D6A0',
  moving: '#00D4FF',
  scanning: '#4DA8DA',
  returning: '#F4A261',
  charging: '#FFD166',
  offline: '#6C757D',
}

const STATUS_LABELS = {
  idle: 'Idle — awaiting orders',
  moving: 'En route to waypoint',
  scanning: 'Scanning area',
  returning: 'Returning to base',
  charging: 'Charging at base',
  offline: 'Offline — no power',
}

function PowerBar({ power }) {
  const color = power <= 20 ? '#E63946' : power <= 40 ? '#F4A261' : '#06D6A0'
  return (
    <div className="w-full h-1 rounded-full" style={{ background: '#1E3A5F' }}>
      <div className="h-full rounded-full transition-all duration-500"
        style={{ width: `${power}%`, background: color }} />
    </div>
  )
}

function UAVCard({ uav, onRemove }) {
  const statusColor = STATUS_COLORS[uav.status] || '#6C757D'
  const isActive = uav.status !== 'offline' && uav.status !== 'charging'
  const isAgent = uav.command_source === 'agent'

  return (
    <div className="p-2 mb-1.5 rounded group transition-all"
      style={{ background: '#0B1426', border: `1px solid ${isActive ? statusColor + '40' : '#1E3A5F'}` }}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full"
            style={{ background: statusColor, boxShadow: isActive ? `0 0 6px ${statusColor}80` : 'none' }} />
          <span className="font-mono text-xs font-semibold" style={{ color: '#00D4FF' }}>{uav.id}</span>
          {isAgent && (
            <span className="px-1 rounded text-[9px] font-mono"
              style={{ background: 'rgba(77,168,218,0.15)', color: '#4DA8DA' }}>AI</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] uppercase" style={{ color: statusColor }}>{uav.status}</span>
          <button onClick={() => onRemove(uav.id)}
            className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 text-[10px] px-1 rounded"
            style={{ color: '#E63946', background: 'rgba(230,57,70,0.1)' }}
            title={`Remove ${uav.id}`}>
            x
          </button>
        </div>
      </div>

      <div className="text-[10px] mb-1.5" style={{ color: 'rgba(255,255,255,0.35)' }}>
        {STATUS_LABELS[uav.status] || uav.status}
      </div>

      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-[10px]"
          style={{ color: uav.power <= 20 ? '#E63946' : 'rgba(255,255,255,0.6)' }}>
          {Math.round(uav.power)}%{uav.power <= 20 && ' LOW'}
        </span>
        <span className="font-mono text-[10px]" style={{ color: 'rgba(255,255,255,0.4)' }}>
          ({uav.x},{uav.y})
        </span>
      </div>
      <PowerBar power={uav.power} />

      {uav.sector_id && (
        <div className="mt-1.5 font-mono text-[10px]" style={{ color: 'rgba(255,255,255,0.35)' }}>
          {uav.sector_id}
        </div>
      )}
    </div>
  )
}

function ConfigPanel() {
  const fleet = useMissionStore(s => s.fleet)
  const missionStatus = useMissionStore(s => s.missionStatus)
  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState({ grid_size: 20, num_uavs: 5, num_objectives: 8, num_obstacles: 15, speed: 1.0 })

  const disabled = missionStatus === 'running'

  const reload = () => {
    sendCommand('reload', cfg)
  }

  const setSpeed = (spd) => {
    setCfg(c => ({ ...c, speed: spd }))
    sendCommand('set_speed', { speed: spd })
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="w-full text-[10px] font-mono py-1.5 rounded flex items-center justify-center gap-1"
        style={{ background: 'rgba(77,168,218,0.08)', color: '#4DA8DA', border: '1px solid rgba(77,168,218,0.2)' }}>
        Settings
      </button>
    )
  }

  return (
    <div className="rounded p-2 text-[10px] font-mono space-y-2"
      style={{ background: '#0B1426', border: '1px solid #1E3A5F' }}>
      <div className="flex items-center justify-between">
        <span style={{ color: '#4DA8DA' }}>SIM CONFIG</span>
        <button onClick={() => setOpen(false)} className="px-1" style={{ color: 'rgba(255,255,255,0.3)' }}>x</button>
      </div>

      {/* Speed — always available */}
      <div>
        <label style={{ color: 'rgba(255,255,255,0.4)' }}>Speed</label>
        <div className="flex gap-1 mt-0.5">
          {[0.5, 1, 2, 3].map(s => (
            <button key={s} onClick={() => setSpeed(s)}
              className="flex-1 py-0.5 rounded"
              style={{
                background: Math.abs(cfg.speed - s) < 0.1 ? 'rgba(77,168,218,0.25)' : 'rgba(30,58,95,0.3)',
                color: Math.abs(cfg.speed - s) < 0.1 ? '#4DA8DA' : 'rgba(255,255,255,0.4)',
              }}>
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* World params — only when idle */}
      <div style={{ opacity: disabled ? 0.4 : 1 }}>
        <label style={{ color: 'rgba(255,255,255,0.4)' }}>Grid Size</label>
        <input type="range" min="8" max="40" value={cfg.grid_size} disabled={disabled}
          onChange={e => setCfg(c => ({ ...c, grid_size: +e.target.value }))}
          className="w-full h-1 mt-0.5 accent-cyan-500" />
        <div className="text-right" style={{ color: 'rgba(255,255,255,0.3)' }}>{cfg.grid_size}x{cfg.grid_size}</div>
      </div>

      <div className="grid grid-cols-3 gap-1.5" style={{ opacity: disabled ? 0.4 : 1 }}>
        <div>
          <label style={{ color: 'rgba(255,255,255,0.4)' }}>UAVs</label>
          <input type="number" min="1" max="10" value={cfg.num_uavs} disabled={disabled}
            onChange={e => setCfg(c => ({ ...c, num_uavs: +e.target.value }))}
            className="w-full mt-0.5 px-1 py-0.5 rounded text-center"
            style={{ background: '#1E3A5F', color: '#fff', border: 'none' }} />
        </div>
        <div>
          <label style={{ color: 'rgba(255,255,255,0.4)' }}>Targets</label>
          <input type="number" min="1" max="20" value={cfg.num_objectives} disabled={disabled}
            onChange={e => setCfg(c => ({ ...c, num_objectives: +e.target.value }))}
            className="w-full mt-0.5 px-1 py-0.5 rounded text-center"
            style={{ background: '#1E3A5F', color: '#fff', border: 'none' }} />
        </div>
        <div>
          <label style={{ color: 'rgba(255,255,255,0.4)' }}>Obstacles</label>
          <input type="number" min="0" max="50" value={cfg.num_obstacles} disabled={disabled}
            onChange={e => setCfg(c => ({ ...c, num_obstacles: +e.target.value }))}
            className="w-full mt-0.5 px-1 py-0.5 rounded text-center"
            style={{ background: '#1E3A5F', color: '#fff', border: 'none' }} />
        </div>
      </div>

      <button onClick={reload} disabled={disabled}
        className="w-full py-1 rounded font-semibold"
        style={{
          background: disabled ? '#1E3A5F' : '#F4A261',
          color: disabled ? 'rgba(255,255,255,0.3)' : '#0B1426',
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}>
        REBUILD WORLD
      </button>
      {disabled && (
        <div className="text-center" style={{ color: 'rgba(255,255,255,0.25)' }}>
          Pause or stop mission to change world params
        </div>
      )}
    </div>
  )
}

export default function FleetPanel() {
  const fleet = useMissionStore(s => s.fleet)

  const active = fleet.filter(u => u.status !== 'offline')
  const offline = fleet.filter(u => u.status === 'offline')

  const addUav = () => sendCommand('add_uav', {})
  const removeUav = (id) => sendCommand('remove_uav', { uav_id: id })

  return (
    <div className="h-full flex flex-col" style={{ background: '#111B2E' }}>
      <div className="panel-header flex items-center justify-between">
        <span>Fleet Status</span>
        <div className="flex items-center gap-1">
          <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{active.length} active</span>
          <button onClick={addUav}
            className="text-[10px] px-1.5 py-0.5 rounded font-bold"
            style={{ background: 'rgba(6,214,160,0.15)', color: '#06D6A0' }}
            title="Add UAV">+</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {fleet.length === 0 && (
          <div className="text-center py-6 font-mono text-xs" style={{ color: 'rgba(255,255,255,0.3)' }}>
            No UAVs deployed
          </div>
        )}
        {active.map(uav => <UAVCard key={uav.id} uav={uav} onRemove={removeUav} />)}
        {offline.length > 0 && (
          <>
            <div className="text-[10px] font-mono uppercase tracking-wider mt-3 mb-1 px-1"
              style={{ color: 'rgba(255,255,255,0.2)' }}>Offline</div>
            {offline.map(uav => <UAVCard key={uav.id} uav={uav} onRemove={removeUav} />)}
          </>
        )}
      </div>

      {/* Config panel at bottom */}
      <div className="p-2 border-t" style={{ borderColor: '#1E3A5F' }}>
        <ConfigPanel />
      </div>
    </div>
  )
}
