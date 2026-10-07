import Phaser from 'phaser'
import './style.css'
import { api, type RunEvent } from './api.ts'
import { signIn, signOut } from './auth.ts'
import { OfficeScene } from './scenes/OfficeScene.ts'

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!

async function start(): Promise<void> {
  await signIn()
  const [me, employees] = await Promise.all([api.me(), api.employees()])

  $('#company').textContent = me.tenant_name
  $('#sign-out').addEventListener('click', () => void signOut())

  const scene = new OfficeScene({ employees })
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
    scene,
  })
  await scene.loaded

  $<HTMLFormElement>('#goal-form').addEventListener('submit', (submit) => {
    submit.preventDefault()
    const input = $<HTMLInputElement>('#goal')
    void runGoal(scene, input.value.trim()).catch((error: unknown) => status(`Run failed: ${String(error)}`))
    input.value = ''
  })
}

async function runGoal(scene: OfficeScene, goal: string): Promise<void> {
  const button = $<HTMLButtonElement>('#goal-form button')
  button.disabled = true
  try {
    const run = await api.startRun(goal)
    status(`Working on "${goal}"…`)
    await api.followRun(run.id, (event: RunEvent) => {
      scene.show(event)
      if (event.type === 'run_finished') status(event.summary)
      if (event.type === 'run_failed') status(`The run failed (${event.error}).`)
    })
  } finally {
    button.disabled = false
  }
}

function status(text: string): void {
  $('#status').textContent = text
}

start().catch((error: unknown) => {
  $('#office').textContent = `Could not open the office: ${String(error)}`
})
