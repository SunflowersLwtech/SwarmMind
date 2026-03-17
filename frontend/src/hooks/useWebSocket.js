import { useEffect, useRef, useCallback } from 'react'
import useMissionStore from '../stores/missionStore'

const WS_URL = `ws://${window.location.hostname}:8000/ws/live`

export default function useWebSocket() {
  const wsRef = useRef(null)
  const attemptRef = useRef(0)
  const timerRef = useRef(null)
  const intentionalRef = useRef(false)

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      useMissionStore.getState().setConnected(true)
      attemptRef.current = 0
      console.log('[WS] Connected')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'state_update' || msg.type === 'initial_state') {
          useMissionStore.getState().updateState(msg.payload)
        }
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }

    ws.onerror = () => {}

    ws.onclose = () => {
      useMissionStore.getState().setConnected(false)
      wsRef.current = null

      if (!intentionalRef.current && attemptRef.current < 10) {
        const delay = Math.min(1000 * Math.pow(2, attemptRef.current), 30000)
        attemptRef.current += 1
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${attemptRef.current})`)
        timerRef.current = setTimeout(connect, delay)
      }
    }
  }, [])

  useEffect(() => {
    intentionalRef.current = false
    connect()
    return () => {
      intentionalRef.current = true
      clearTimeout(timerRef.current)
      if (wsRef.current) wsRef.current.close(1000)
    }
  }, [connect])

  const sendCommand = useCallback((type, payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, payload }))
    }
  }, [])

  return { sendCommand }
}
