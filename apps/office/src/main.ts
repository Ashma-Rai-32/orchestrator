import Phaser from 'phaser'
import './style.css'
import { api } from './api.ts'
import { signIn, signOut } from './auth.ts'
import { OfficeScene } from './scenes/OfficeScene.ts'

async function start(): Promise<void> {
  await signIn()
  const [me, employees] = await Promise.all([api.me(), api.employees()])

  document.querySelector('#company')!.textContent = me.tenant_name
  document.querySelector('#sign-out')!.addEventListener('click', () => void signOut())

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
    scene: new OfficeScene({ employees }),
  })
}

start().catch((error: unknown) => {
  document.querySelector('#office')!.textContent = `Could not open the office: ${String(error)}`
})
