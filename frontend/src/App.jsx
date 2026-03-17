import { useEffect } from 'react'
import TacticalMap from './scene/TacticalMap'
import GlobalStatusBar from './panels/GlobalStatusBar'
import FleetPanel from './panels/FleetPanel'
import CommandConsole from './panels/CommandConsole'
import OpDashboard from './panels/OpDashboard'
import EventTimeline from './panels/EventTimeline'
import useWebSocket from './hooks/useWebSocket'

export default function App() {
  // Establish WebSocket connection on mount
  useWebSocket()

  return (
    <div className="w-full h-full flex flex-col" style={{ background: '#0B1426' }}>
      {/* Top: Global Status Bar */}
      <GlobalStatusBar />

      {/* Middle: Three-column layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Fleet Panel */}
        <div className="w-56 shrink-0 border-r" style={{ borderColor: '#1E3A5F' }}>
          <FleetPanel />
        </div>

        {/* Center: 3D Tactical Map */}
        <div className="flex-1 relative">
          <TacticalMap />
        </div>

        {/* Right: Command Console + Dashboard */}
        <div className="w-64 shrink-0 border-l flex flex-col" style={{ borderColor: '#1E3A5F' }}>
          <div className="flex-1 overflow-hidden">
            <CommandConsole />
          </div>
          <div className="border-t" style={{ borderColor: '#1E3A5F' }}>
            <OpDashboard />
          </div>
        </div>
      </div>

      {/* Bottom: Event Timeline */}
      <EventTimeline />
    </div>
  )
}
