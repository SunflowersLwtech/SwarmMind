import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

export default function CoverageOverlay() {
  const meshRef = useRef()
  const gridSize = useMissionStore(state => state.gridSize)

  const cellGeo = useMemo(() => new THREE.PlaneGeometry(0.92, 0.92), [])

  // Use a single instanced mesh for all cells
  const maxCells = gridSize * gridSize
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const colors = useMemo(() => new Float32Array(maxCells * 3), [maxCells])

  useFrame(() => {
    const { exploredGrid, heatmap, obstacles } = useMissionStore.getState()
    if (!meshRef.current) return

    const exploredSet = new Set(exploredGrid.map(([x, y]) => `${x},${y}`))
    const obstacleSet = new Set(obstacles.map(([x, y]) => `${x},${y}`))

    let idx = 0
    for (let x = 0; x < gridSize; x++) {
      for (let y = 0; y < gridSize; y++) {
        const key = `${x},${y}`
        dummy.position.set(x, 0.02, y)
        dummy.rotation.set(-Math.PI / 2, 0, 0)
        dummy.updateMatrix()
        meshRef.current.setMatrixAt(idx, dummy.matrix)

        if (obstacleSet.has(key)) {
          colors[idx * 3] = 0.15
          colors[idx * 3 + 1] = 0.08
          colors[idx * 3 + 2] = 0.08
        } else if (exploredSet.has(key)) {
          // Explored = green tint
          colors[idx * 3] = 0.02
          colors[idx * 3 + 1] = 0.15
          colors[idx * 3 + 2] = 0.08
        } else {
          // Unexplored = show heatmap probability
          const prob = (heatmap && heatmap[x] && heatmap[x][y]) || 0
          if (prob > 0.3) {
            // High probability = warm
            colors[idx * 3] = prob * 0.8
            colors[idx * 3 + 1] = prob * 0.2
            colors[idx * 3 + 2] = 0.05
          } else {
            // Low probability = dim
            colors[idx * 3] = 0.04
            colors[idx * 3 + 1] = 0.06
            colors[idx * 3 + 2] = 0.1
          }
        }
        idx++
      }
    }

    meshRef.current.instanceMatrix.needsUpdate = true
    meshRef.current.instanceColor = new THREE.InstancedBufferAttribute(colors, 3)
    meshRef.current.instanceColor.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[cellGeo, null, maxCells]}>
      <meshBasicMaterial transparent opacity={0.4} />
    </instancedMesh>
  )
}
