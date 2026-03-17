import { useRef, useEffect, useState } from 'react'
import useMissionStore from '../stores/missionStore'
import useWebSocket from '../hooks/useWebSocket'

export default function CommandConsole() {
  const events = useMissionStore(s => s.events)
  const missionStatus = useMissionStore(s => s.missionStatus)
  const logRef = useRef(null)
  const { sendCommand } = useWebSocket()

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [events])

  return (
    <div className="h-full flex flex-col" style={{ background: '#111B2E' }}>
      <div className="panel-header">Mission Log</div>

      {/* Event log */}
      <div
        ref={logRef}
        className="flex-1 overflow-y-auto p-2 font-mono text-xs"
        style={{ color: 'rgba(255,255,255,0.7)' }}
      >
        {events.length === 0 && (
          <div className="text-center py-4" style={{ color: 'rgba(255,255,255,0.3)' }}>
            Awaiting mission start...
          </div>
        )}
        {events.map((evt, i) => (
          <div key={i} className="log-entry py-0.5 border-b" style={{ borderColor: 'rgba(30,58,95,0.3)' }}>
            <span style={{ color: '#4DA8DA' }}>&gt; </span>
            {evt}
          </div>
        ))}
      </div>

      {/* Control buttons */}
      <div className="p-2 border-t flex gap-1.5" style={{ borderColor: '#1E3A5F' }}>
        {missionStatus === 'idle' && (
          <button
            onClick={() => sendCommand('start')}
            className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
            style={{ background: '#06D6A0', color: '#0B1426' }}
          >
            START
          </button>
        )}
        {missionStatus === 'running' && (
          <button
            onClick={() => sendCommand('pause')}
            className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
            style={{ background: '#F4A261', color: '#0B1426' }}
          >
            PAUSE
          </button>
        )}
        {missionStatus === 'paused' && (
          <>
            <button
              onClick={() => sendCommand('resume')}
              className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
              style={{ background: '#06D6A0', color: '#0B1426' }}
            >
              RESUME
            </button>
            <button
              onClick={() => sendCommand('stop')}
              className="flex-1 py-1.5 rounded font-mono text-xs font-semibold"
              style={{ background: '#E63946', color: 'white' }}
            >
              STOP
            </button>
          </>
        )}
        <button
          onClick={() => sendCommand('reset')}
          className="px-3 py-1.5 rounded font-mono text-xs"
          style={{ background: '#1E3A5F', color: 'rgba(255,255,255,0.6)' }}
        >
          RESET
        </button>
      </div>
    </div>
  )
}
