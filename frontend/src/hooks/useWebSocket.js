/**
 * Module-level WebSocket singleton — immune to React StrictMode.
 *
 * The connection lives at module scope, completely outside React lifecycle.
 * Components call useWebSocket() to get sendCommand; the hook only
 * subscribes/unsubscribes (cheap & idempotent), never owns the socket.
 */
import { useEffect } from 'react'
import useMissionStore from '../stores/missionStore'

// Auto-detect ws:// vs wss:// based on page protocol (HTTPS on Render)
const WS_PROTO = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS_URL = `${WS_PROTO}//${window.location.host}/ws/live`
const MAX_ATTEMPTS = 10

let ws = null
let attempt = 0
let timer = null

function handleMessage(event) {
  try {
    const msg = JSON.parse(event.data)
    const store = useMissionStore.getState()
    if (msg.type === 'state_update' || msg.type === 'initial_state') {
      store.updateState(msg.payload)
    } else if (msg.type === 'agent_log') {
      store.addLog(msg.payload)
    } else if (msg.type === 'agent_status') {
      store.setAgentStatus(msg.payload.status, msg.payload.cycle)
    }
  } catch (e) {
    console.error('[WS] Parse error:', e)
  }
}

function connect() {
  if (ws && ws.readyState !== WebSocket.CLOSED) return

  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    useMissionStore.getState().setConnected(true)
    attempt = 0
    console.log('[WS] Connected')
  }

  ws.onmessage = handleMessage

  ws.onerror = (err) => {
    console.error('[WS] Connection error:', err)
  }

  ws.onclose = () => {
    useMissionStore.getState().setConnected(false)
    ws = null
    if (attempt < MAX_ATTEMPTS) {
      const delay = Math.min(1000 * Math.pow(2, attempt), 30000)
      attempt += 1
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${attempt})`)
      timer = setTimeout(connect, delay)
    }
  }
}

/** Send a command via WebSocket. Returns true if sent. */
export function sendCommand(type, payload) {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, payload }))
    return true
  }
  return false
}

// Defer first connection to avoid racing with Vite proxy startup
setTimeout(connect, 100)

/**
 * React hook — ensures reconnection if module was loaded before
 * the backend was ready. Components use this for sendCommand access.
 */
export default function useWebSocket() {
  useEffect(() => {
    // If not connected, kick off a reconnect
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      attempt = 0
      clearTimeout(timer)
      connect()
    }
    // No cleanup needed — singleton lives for page lifetime
  }, [])

  return { sendCommand }
}
