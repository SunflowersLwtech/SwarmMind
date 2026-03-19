import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

const TRAIL_LENGTH = 40
const TRAIL_Y = 0.08

const UAV_COLORS = {
  Alpha:   [0, 0.83, 1],
  Bravo:   [0.06, 0.8, 0.4],
  Charlie: [1, 0.6, 0.15],
  Delta:   [0.8, 0.3, 0.9],
  Echo:    [1, 0.82, 0.4],
}

function Trail({ uavId, color }) {
  const lineRef = useRef()
  const historyRef = useRef([])

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry()
    const positions = new Float32Array(TRAIL_LENGTH * 3)
    const alphas = new Float32Array(TRAIL_LENGTH)
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geo.setAttribute('alpha', new THREE.BufferAttribute(alphas, 1))
    return geo
  }, [])

  useFrame(() => {
    const fleet = useMissionStore.getState().fleet
    const uav = fleet.find(u => u.id === uavId)
    if (!uav || !lineRef.current) return

    const history = historyRef.current
    const last = history[history.length - 1]
    if (!last || last[0] !== uav.x || last[1] !== uav.y) {
      history.push([uav.x, uav.y])
      if (history.length > TRAIL_LENGTH) history.shift()
    }

    const positions = geometry.attributes.position.array
    const alphas = geometry.attributes.alpha.array
    const len = history.length

    for (let i = 0; i < TRAIL_LENGTH; i++) {
      if (i < len) {
        const [x, y] = history[i]
        positions[i * 3] = x
        positions[i * 3 + 1] = TRAIL_Y
        positions[i * 3 + 2] = y
        alphas[i] = (i + 1) / len
      } else {
        positions[i * 3] = 0
        positions[i * 3 + 1] = -10
        positions[i * 3 + 2] = 0
        alphas[i] = 0
      }
    }

    geometry.attributes.position.needsUpdate = true
    geometry.attributes.alpha.needsUpdate = true
    geometry.setDrawRange(0, len)
  })

  return (
    <line ref={lineRef} geometry={geometry}>
      <lineBasicMaterial
        color={new THREE.Color(...color)}
        transparent
        opacity={0.5}
        linewidth={1}
      />
    </line>
  )
}

export default function PathTrails() {
  const fleet = useMissionStore(s => s.fleet)

  return (
    <group>
      {fleet.map(uav => (
        <Trail
          key={uav.id}
          uavId={uav.id}
          color={UAV_COLORS[uav.id] || [0.5, 0.5, 0.5]}
        />
      ))}
    </group>
  )
}
