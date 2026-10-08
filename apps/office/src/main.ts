import Phaser from 'phaser'
import './style.css'
import { api, type InboxItem, type RunEvent } from './api.ts'
import { signIn, signOut } from './auth.ts'
import { OfficeScene } from './scenes/OfficeScene.ts'

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!

let scene: OfficeScene
const following = new Set<string>() // runs whose live stream is open

async function start(): Promise<void> {
  await signIn()
  const [me, employees] = await Promise.all([api.me(), api.employees()])

  $('#company').textContent = me.tenant_name
  $('#sign-out').addEventListener('click', () => void signOut())

  scene = new OfficeScene({ employees })
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
    void startGoal(input.value.trim()).catch((error: unknown) => status(`Could not start: ${String(error)}`))
    input.value = ''
  })

  // Questions may be waiting from runs started earlier (or while signed out).
  const open = await refreshInbox()
  for (const runId of new Set(open.map((item) => item.run_id))) void follow(runId)
}

async function startGoal(goal: string): Promise<void> {
  const run = await api.startRun(goal)
  status(`Working on "${goal}"…`)
  await follow(run.id)
}

/** Stream a run into the office until it ends; paused runs keep the stream open. */
async function follow(runId: string): Promise<void> {
  if (following.has(runId)) return
  following.add(runId)
  try {
    await api.followRun(runId, (event: RunEvent) => {
      scene.show(event)
      if (event.type === 'input_needed') void refreshInbox()
      if (event.type === 'run_waiting') status('Your team has a question for you: see the inbox.')
      if (event.type === 'run_finished') status(event.summary)
      if (event.type === 'run_failed') status(`The run failed (${event.error}).`)
    })
  } finally {
    following.delete(runId)
  }
}

async function refreshInbox(): Promise<InboxItem[]> {
  const items = await api.inbox()
  const list = $<HTMLUListElement>('#inbox-items')
  list.replaceChildren(...items.map(renderQuestion))
  $('#inbox').hidden = items.length === 0
  return items
}

function renderQuestion(item: InboxItem): HTMLLIElement {
  // Questions are model output: textContent only, never innerHTML.
  const who = document.createElement('strong')
  who.textContent = item.employee
  const question = document.createElement('p')
  question.append(who, ` asks: ${item.question}`)

  const input = document.createElement('input')
  input.required = true
  input.maxLength = 8000
  input.placeholder = 'Your answer'
  if (item.secret_name) {
    // A credential: masked, not remembered by the browser, stored in OpenBao by the API.
    input.type = 'password'
    input.autocomplete = 'off'
    input.placeholder = `Paste the key (stored securely as ${item.secret_name})`
    const note = document.createElement('small')
    note.textContent = `Your team will only ever see the name ${item.secret_name}, never the value.`
    question.append(document.createElement('br'), note)
  }
  const send = document.createElement('button')
  send.type = 'submit'
  send.textContent = 'Send'
  const form = document.createElement('form')
  form.append(input, send)
  form.addEventListener('submit', (submit) => {
    submit.preventDefault()
    send.disabled = true
    const text = input.value.trim()
    input.value = '' // don't leave a pasted key sitting in the page
    void answer(item, text).finally(() => (send.disabled = false))
  })

  const li = document.createElement('li')
  li.append(question, form)
  return li
}

async function answer(item: InboxItem, text: string): Promise<void> {
  try {
    const { run_resumed } = await api.answer(item.id, text)
    status(run_resumed ? 'Thanks! Your team is back at work.' : 'Thanks! Other questions are still open.')
    await refreshInbox()
    if (run_resumed) void follow(item.run_id) // no-op if already streaming
  } catch (error: unknown) {
    status(`Could not send the answer: ${String(error)}`)
  }
}

function status(text: string): void {
  $('#status').textContent = text
}

start().catch((error: unknown) => {
  $('#office').textContent = `Could not open the office: ${String(error)}`
})
