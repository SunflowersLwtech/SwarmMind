import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

export default function CoverageOverlay() {
  const meshRef = useRef()
  const gridSize = useMissionStore(state => state.gridSize)
  const lastTickRef = useRef(-1)

  const cellGeo = useMemo(() => new THREE.PlaneGeometry(0.92, 0.92), [])
  const maxCells = gridSize * gridSize
  const dummy = useMemo(() => new THREE.Object3D(), [])

  // Pre-allocate color buffer once — reuse across frames
  const colorArr = useMemo(() => new Float32Array(maxCells * 3), [maxCells])
  const colorAttr = useMemo(() => {
    const attr = new THREE.InstancedBufferAttribute(colorArr, 3)
    attr.setUsage(THREE.DynamicDrawUsage)
    return attr
  }, [colorArr])

  // Set instance color once on mount
  const initRef = useRef(false)

  useFrame(() => {
    const { exploredGrid, heatmap, obstacles, tick } = useMissionStore.getState()
    if (!meshRef.current) return

    // Attach color attribute once
    if (!initRef.current) {
      meshRef.current.instanceColor = colorAttr
      initRef.current = true
    }

    // Only update when tick changes (state_update arrived)
    if (tick === lastTickRef.current) return
    lastTickRef.current = tick

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
          colorArr[idx * 3] = 0.15
          colorArr[idx * 3 + 1] = 0.08
          colorArr[idx * 3 + 2] = 0.08
        } else if (exploredSet.has(key)) {
          colorArr[idx * 3] = 0.02
          colorArr[idx * 3 + 1] = 0.15
          colorArr[idx * 3 + 2] = 0.08
        } else {
          const prob = (heatmap && heatmap[x] && heatmap[x][y]) || 0
          if (prob > 0.3) {
            colorArr[idx * 3] = prob * 0.8
            colorArr[idx * 3 + 1] = prob * 0.2
            colorArr[idx * 3 + 2] = 0.05
          } else {
            colorArr[idx * 3] = 0.04
            colorArr[idx * 3 + 1] = 0.06
            colorArr[idx * 3 + 2] = 0.1
          }
        }
        idx++
      }
    }

    meshRef.current.instanceMatrix.needsUpdate = true
    colorAttr.needsUpdate = true
  })

  return (
    <instancedMesh ref={meshRef} args={[cellGeo, null, maxCells]}>
      <meshBasicMaterial transparent opacity={0.4} />
    </instancedMesh>
  )
}
