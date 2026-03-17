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
  missionTime: 0,
  tick: 0,
  objectivesFound: 0,
  objectivesTotal: 0,

  // Agent CoT logs
  agentLogs: [],

  // Events timeline
  events: [],

  // Connection
  connected: false,

  // Actions
  updateState: (payload) => set({
    fleet: payload.fleet || get().fleet,
    coverage: payload.coverage_pct ?? get().coverage,
    objectives: payload.objectives || get().objectives,
    exploredGrid: payload.explored || get().exploredGrid,
    obstacles: payload.obstacles || get().obstacles,
    heatmap: payload.heatmap || get().heatmap,
    hotspots: payload.hotspots || get().hotspots,
    gridSize: payload.grid_size || get().gridSize,
    base: payload.base || get().base,
    sectors: payload.sectors || get().sectors,
    missionStatus: payload.mission_status || get().missionStatus,
    tick: payload.tick ?? get().tick,
    objectivesFound: payload.objectives_found ?? get().objectivesFound,
    objectivesTotal: payload.objectives_total ?? get().objectivesTotal,
    events: payload.events || get().events,
  }),

  addLog: (log) => set(state => ({
    agentLogs: [...state.agentLogs.slice(-99), log],
  })),

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
    events: [],
  }),
}))

export default useMissionStore
