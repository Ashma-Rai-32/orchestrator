import Phaser from 'phaser'
import './style.css'
import { OfficeScene } from './scenes/OfficeScene.ts'

new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'office',
  // Full-resolution canvas; the camera zooms 2x (game `zoom` would CSS-upscale a
  // half-size canvas, blurring text). Not `pixelArt: true`: art textures opt into
  // NEAREST filtering in the scene, text keeps smooth filtering.
  width: 30 * 16 * 2,
  height: 20 * 16 * 2,
  antialias: true,
  roundPixels: true,
  backgroundColor: '#1d2029',
  scene: [OfficeScene],
})
