import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'
import useMissionStore from '../stores/missionStore'

export default function ObjectiveMarkers() {
  const objectives = useMissionStore(state => state.objectives)
  const refs = useRef({})

  useFrame(() => {
    const objs = useMissionStore.getState().objectives
    objs.forEach(obj => {
      const ref = refs.current[obj.id]
      if (ref && obj.detected) {
        // Detected: gentle glow pulse
        ref.scale.setScalar(1 + Math.sin(Date.now() * 0.005) * 0.1)
      }
    })
  })

  return (
    <group>
      {objectives.filter(o => o.detected).map(obj => (
        <group key={obj.id}>
          <group
            ref={el => { if (el) refs.current[obj.id] = el }}
            position={[obj.x, 0.5, obj.y]}
          >
            <mesh>
              <octahedronGeometry args={[0.2, 0]} />
              <meshStandardMaterial
                color="#E63946"
                emissive="#E63946"
                emissiveIntensity={0.8}
              />
            </mesh>
            {/* Rescue ring */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.4, 0]}>
              <ringGeometry args={[0.3, 0.5, 16]} />
              <meshBasicMaterial color="#E63946" transparent opacity={0.3} side={THREE.DoubleSide} />
            </mesh>
          </group>
          <Billboard position={[obj.x, 1.2, obj.y]} follow>
            <Text fontSize={0.25} color="#E63946">
              {obj.claimed_by ? `${obj.id} [${obj.claimed_by}]` : obj.id}
            </Text>
          </Billboard>
        </group>
      ))}
    </group>
  )
}
