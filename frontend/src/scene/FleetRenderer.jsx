import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

const _pos = new THREE.Vector3()

function statusColor(status, power) {
  if (status === 'offline') return '#6C757D'
  if (status === 'charging') return '#FFD166'
  if (power <= 20) return '#E63946'
  if (power <= 40) return '#F4A261'
  return '#00D4FF'
}

function UAVLabel({ uav }) {
  return (
    <Billboard position={[uav.x, 1.8, uav.y]} follow>
      <Text
        fontSize={0.35}
        color={statusColor(uav.status, uav.power)}
        anchorY="bottom"
        font={undefined}
      >
        {uav.id}
      </Text>
      <Text
        fontSize={0.22}
        color="rgba(255,255,255,0.6)"
        position={[0, -0.35, 0]}
        font={undefined}
      >
        {Math.round(uav.power)}%
      </Text>
    </Billboard>
  )
}

export default function FleetRenderer() {
  const fleet = useMissionStore(state => state.fleet)
  const instanceRefs = useRef({})

  // Smoothly interpolate positions in useFrame
  useFrame((_, delta) => {
    const currentFleet = useMissionStore.getState().fleet
    currentFleet.forEach(uav => {
      const ref = instanceRefs.current[uav.id]
      if (ref) {
        _pos.set(uav.x, 0.5, uav.y)
        ref.position.lerp(_pos, 1 - Math.exp(-8 * delta))
        // Gentle hover animation
        ref.position.y = 0.5 + Math.sin(Date.now() * 0.003 + uav.x) * 0.05
      }
    })
  })

  return (
    <group>
      {fleet.map(uav => (
        <group key={uav.id}>
          <group ref={el => { if (el) instanceRefs.current[uav.id] = el }} position={[uav.x, 0.5, uav.y]}>
            {/* UAV body - octahedron shape */}
            <mesh>
              <octahedronGeometry args={[0.25, 0]} />
              <meshStandardMaterial
                color={statusColor(uav.status, uav.power)}
                emissive={statusColor(uav.status, uav.power)}
                emissiveIntensity={0.6}
                metalness={0.8}
                roughness={0.2}
              />
            </mesh>
            {/* Sensor range ring */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.45, 0]}>
              <ringGeometry args={[uav.sensor_range - 0.1, uav.sensor_range, 32]} />
              <meshBasicMaterial color="#00D4FF" transparent opacity={0.1} side={THREE.DoubleSide} />
            </mesh>
          </group>
          <UAVLabel uav={uav} />
        </group>
      ))}
    </group>
  )
}
