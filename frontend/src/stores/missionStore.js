import { create } from 'zustand'

const useMissionStore = create((set, get) => ({
  // Fleet state
  fleet: [],
  coverage: 0,
  objectives: [],
  exploredGrid: [],
  obstacles: [],
  heatmap: [],
  hotspots: [],
  gridSize: 20,
  base: [0, 0],
  sectors: null,

  // Mission state
  missionStatus: 'idle',
  tick: 0,
  objectivesFound: 0,
  objectivesTotal: 0,

  // Agent CoT logs
  agentLogs: [],
  agentStatus: 'idle',
  agentCycle: 0,

  // Events timeline
  events: [],

  // Connection
  connected: false,

  // Actions
  updateState: (payload) => set(state => {
    const newEvents = payload.events || state.events
    let newLogs = []
    if (newEvents.length > state.events.length) {
      newLogs = newEvents.slice(state.events.length).map(evt => ({
        timestamp: Date.now(),
        action: 'system_event',
        agent: 'SYS',
        detail: evt
      }))
    }

    return {
      fleet: payload.fleet || state.fleet,
      coverage: payload.coverage_pct ?? state.coverage,
      objectives: payload.objectives || state.objectives,
      exploredGrid: payload.explored || state.exploredGrid,
      obstacles: payload.obstacles || state.obstacles,
      heatmap: payload.heatmap || state.heatmap,
      hotspots: payload.hotspots || state.hotspots,
      gridSize: payload.grid_size || state.gridSize,
      base: payload.base || state.base,
      sectors: payload.sectors || state.sectors,
      missionStatus: payload.mission_status || state.missionStatus,
      tick: payload.tick ?? state.tick,
      objectivesFound: payload.objectives_found ?? state.objectivesFound,
      objectivesTotal: payload.objectives_total ?? state.objectivesTotal,
      events: newEvents,
      agentLogs: newLogs.length > 0 ? [...state.agentLogs.slice(-(99 - newLogs.length)), ...newLogs] : state.agentLogs,
    }
  }),

  addLog: (log) => set(state => {
    // Deduplicate/Update: if last log has same timestamp+action+agent, update it (for streaming text)
    const last = state.agentLogs[state.agentLogs.length - 1]
    if (last && last.timestamp === log.timestamp && last.action === log.action && last.agent === log.agent) {
      const updated = [...state.agentLogs]
      updated[updated.length - 1] = log
      return { agentLogs: updated }
    }
    return { agentLogs: [...state.agentLogs.slice(-99), log] }
  }),

  setAgentStatus: (status, cycle) => set({ agentStatus: status, agentCycle: cycle }),

  addEvent: (event) => set(state => ({
    events: [...state.events.slice(-49), event],
  })),

  setConnected: (val) => set({ connected: val }),

  reset: () => set({
    fleet: [],
    coverage: 0,
    objectives: [],
    exploredGrid: [],
    heatmap: [],
    hotspots: [],
    missionStatus: 'idle',
    tick: 0,
    objectivesFound: 0,
    objectivesTotal: 0,
    agentLogs: [],
    agentStatus: 'idle',
    agentCycle: 0,
    events: [],
  }),
}))

export default useMissionStore
