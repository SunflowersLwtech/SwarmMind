import { useMemo } from 'react'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

export default function TerrainMesh() {
  const obstacles = useMissionStore(state => state.obstacles)
  const gridSize = useMissionStore(state => state.gridSize)

  const obstacleGeo = useMemo(() => new THREE.BoxGeometry(0.9, 0.4, 0.9), [])
  const obstacleMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: '#2a1a1a',
    roughness: 0.9,
  }), [])

  // Ground plane
  const groundGeo = useMemo(() => new THREE.PlaneGeometry(gridSize, gridSize), [gridSize])
  const groundMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: '#0d1f2d',
    roughness: 1,
  }), [])

  return (
    <group>
      {/* Ground */}
      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[gridSize / 2 - 0.5, -0.01, gridSize / 2 - 0.5]}
        geometry={groundGeo}
        material={groundMat}
      />

      {/* Base station marker */}
      <mesh position={[0, 0.15, 0]}>
        <cylinderGeometry args={[0.4, 0.4, 0.3, 16]} />
        <meshStandardMaterial color="#06D6A0" emissive="#06D6A0" emissiveIntensity={0.5} />
      </mesh>

      {/* Obstacles */}
      {obstacles.map(([x, y], i) => (
        <mesh
          key={i}
          position={[x, 0.2, y]}
          geometry={obstacleGeo}
          material={obstacleMat}
        />
      ))}
    </group>
  )
}
