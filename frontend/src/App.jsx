import { useState, useCallback, useRef } from 'react'
import TacticalMap from './scene/TacticalMap'
import GlobalStatusBar from './panels/GlobalStatusBar'
import FleetPanel from './panels/FleetPanel'
import CommandConsole from './panels/CommandConsole'
import OpDashboard from './panels/OpDashboard'
import EventTimeline from './panels/EventTimeline'

function ResizeHandle({ onDrag, side }) {
  const dragging = useRef(false)

  const onMouseDown = useCallback((e) => {
    e.preventDefault()
    dragging.current = true
    const startX = e.clientX

    const onMove = (e2) => {
      if (!dragging.current) return
      onDrag(e2.clientX - startX, e2.clientX)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [onDrag])

  return (
    <div
      onMouseDown={onMouseDown}
      className="shrink-0 cursor-col-resize hover:opacity-100 opacity-0 transition-opacity z-10"
      style={{
        width: 5,
        background: 'linear-gradient(to right, transparent, #00D4FF40, transparent)',
      }}
    />
  )
}

export default function App() {
  const [leftW, setLeftW] = useState(224)
  const [rightW, setRightW] = useState(340)

  const onLeftDrag = useCallback((_, clientX) => {
    setLeftW(Math.max(160, Math.min(400, clientX)))
  }, [])

  const onRightDrag = useCallback((_, clientX) => {
    setRightW(Math.max(250, Math.min(600, window.innerWidth - clientX)))
  }, [])

  return (
    <div className="w-full h-full flex flex-col" style={{ background: '#0B1426' }}>
      <GlobalStatusBar />

      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar — resizable */}
        <div className="shrink-0 overflow-hidden flex flex-col" style={{ width: leftW, maxWidth: '40vw', borderRight: '1px solid #1E3A5F' }}>
          <FleetPanel />
        </div>
        <ResizeHandle onDrag={onLeftDrag} side="left" />

        {/* Center: 3D map */}
        <div className="flex-1 relative min-w-0 min-h-0">
          <TacticalMap />
        </div>

        {/* Right sidebar — resizable */}
        <ResizeHandle onDrag={onRightDrag} side="right" />
        <div className="shrink-0 flex flex-col overflow-hidden" style={{ width: rightW, maxWidth: '45vw', borderLeft: '1px solid #1E3A5F' }}>
          <div className="flex-1 overflow-hidden min-h-0">
            <CommandConsole />
          </div>
          <div className="shrink-0 border-t" style={{ borderColor: '#1E3A5F' }}>
            <OpDashboard />
          </div>
      </div>
      </div>
    </div>
  )
}
