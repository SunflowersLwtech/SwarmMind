import { EffectComposer, Bloom, Vignette, Noise } from '@react-three/postprocessing'
import { BlendFunction } from 'postprocessing'

export default function PostFX() {
  return (
    <EffectComposer multisampling={4}>
      <Bloom
        luminanceThreshold={0.6}
        intensity={0.8}
        mipmapBlur
      />
      <Vignette
        offset={0.3}
        darkness={0.7}
        eskil={false}
      />
      <Noise
        blendFunction={BlendFunction.COLOR_DODGE}
        opacity={0.02}
      />
    </EffectComposer>
  )
}
