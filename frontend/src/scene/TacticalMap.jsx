import { Canvas } from '@react-three/fiber'
import { CameraControls, Grid, PerformanceMonitor } from '@react-three/drei'
import { useState } from 'react'
import TerrainMesh from './TerrainMesh'
import FleetRenderer from './FleetRenderer'
import PathTrails from './PathTrails'
import CoverageOverlay from './CoverageOverlay'
import ObjectiveMarkers from './ObjectiveMarkers'
import PostFX from './PostFX'

export default function TacticalMap() {
  const [dpr, setDpr] = useState(1.5)

  return (
    <Canvas
      dpr={dpr}
      camera={{ position: [10, 18, 10], fov: 55 }}
      gl={{ antialias: true, alpha: false }}
      style={{ background: '#0B1426' }}
    >
      <ambientLight intensity={0.3} />
      <directionalLight position={[10, 20, 10]} intensity={0.7} castShadow />

      <TerrainMesh />
      <CoverageOverlay />
      <FleetRenderer />
      <ObjectiveMarkers />

      <Grid
        args={[20, 20]}
        position={[9.5, 0.01, 9.5]}
        cellSize={1}
        sectionSize={5}
        cellColor="#1E3A5F"
        sectionColor="#4DA8DA"
        cellThickness={0.5}
        sectionThickness={1}
        fadeDistance={50}
      />

      <CameraControls
        makeDefault
        minDistance={5}
        maxDistance={40}
        maxPolarAngle={Math.PI / 2.2}
      />

      <PostFX />
      <PerformanceMonitor
        onIncline={() => setDpr(2)}
        onDecline={() => setDpr(1)}
      />
    </Canvas>
  )
}
