import Phaser from 'phaser'
import type { Employee, RunEvent } from '../api.ts'
import { LABEL, Person } from './Person.ts'

/** A named point from the Tiled map's "spots" object layer (desk-1..n, door, huddle). */
type Spot = { name: string; type: string; x: number; y: number }

const TINTS = [0xff8a65, 0xffd54f, 0x81c784, 0x64b5f6, 0xba68c8, 0x4dd0e1, 0xf06292, 0xaed581]
const COORDINATOR_TINT = 0xe0e0e0

export type OfficeData = { employees: Employee[] }

export class OfficeScene extends Phaser.Scene {
  // Not `data`: Phaser.Scene already has a `data` (its DataManager).
  private readonly office: OfficeData
  private readonly people = new Map<string, Person>()
  private coordinator?: Person
  private huddle = { x: 0, y: 0 }
  private ready?: () => void
  /** Resolves once create() has run, so events never arrive before the map. */
  readonly loaded = new Promise<void>((resolve) => (this.ready = resolve))

  constructor(office: OfficeData) {
    super('office')
    this.office = office
  }

  preload(): void {
    this.load.tilemapTiledJSON('office', 'assets/office.tmj')
    this.load.image('office-tiles', 'assets/office-tiles.png')
    this.load.spritesheet('character', 'assets/character.png', { frameWidth: 16, frameHeight: 16 })
  }

  create(): void {
    // Crisp pixel art for art textures only; text keeps smooth filtering.
    for (const key of ['office-tiles', 'character']) {
      this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST)
    }
    const map = this.make.tilemap({ key: 'office' })
    const tiles = map.addTilesetImage('office-tiles', 'office-tiles')
    if (!tiles) throw new Error('tileset "office-tiles" missing from office.tmj')
    map.createLayer('floor', tiles)
    map.createLayer('furniture', tiles)
    this.cameras.main.setZoom(2).centerOn(map.widthInPixels / 2, map.heightInPixels / 2)

    this.anims.create({
      key: 'walk',
      frames: this.anims.generateFrameNumbers('character', { frames: [1, 2] }),
      frameRate: 6,
      repeat: -1,
    })

    const all = spots(map)
    const huddle = all.find((s) => s.name === 'huddle')
    if (!huddle) throw new Error('spot "huddle" missing from office.tmj')
    this.huddle = huddle
    // The platform's coordinator: plans and assigns, never hired by the tenant.
    this.coordinator = new Person(this, 'Coordinator', huddle.x, huddle.y - 8, COORDINATOR_TINT)

    const desks = all.filter((s) => s.type === 'desk')
    const seated = this.office.employees.slice(0, desks.length) // hire order = desk order
    seated.forEach((e, i) => {
      this.people.set(e.name, new Person(this, e.name, desks[i].x, desks[i].y, tintFor(e.name)))
    })

    const standing = this.office.employees.length - seated.length
    if (standing > 0) this.note(`+${standing} without a desk`)
    if (this.office.employees.length === 0) this.note('No one hired yet')
    this.ready?.()
  }

  /** Turn one run event into what people in the office do. */
  show(event: RunEvent): void {
    const boss = this.coordinator
    switch (event.type) {
      case 'run_started':
        boss?.say(`Planning: ${event.goal}`)
        break
      case 'run_resumed':
        boss?.say('Picking up where we left off')
        break
      case 'task_assigned': {
        boss?.say(`${event.employee}, please take this one`)
        const person = this.people.get(event.employee)
        // Walk to the huddle for the brief, then back to the desk to work on it.
        const briefing = { x: this.huddle.x + Phaser.Math.Between(-24, 24), y: this.huddle.y + 12 }
        person?.say('')
        person?.walk([briefing], () => {
          person.say(`Working on: ${event.task}`)
          person.goHome()
        })
        break
      }
      case 'task_finished':
        this.people.get(event.employee)?.say('✓ Done')
        break
      case 'run_finished':
        boss?.say('All done!')
        break
      case 'run_failed':
        boss?.say(`Something went wrong (${event.error})`)
        break
    }
  }

  private note(text: string): void {
    this.add.text(this.huddle.x, this.huddle.y + 24, text, LABEL).setOrigin(0.5).setResolution(4)
  }
}

/** Same person, same colour, on every load. */
function tintFor(name: string): number {
  let hash = 0
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return TINTS[hash % TINTS.length]
}

function spots(map: Phaser.Tilemaps.Tilemap): Spot[] {
  const layer = map.getObjectLayer('spots')
  if (!layer) throw new Error('object layer "spots" missing from office.tmj')
  return layer.objects.map((o) => ({ name: o.name, type: o.type, x: o.x ?? 0, y: o.y ?? 0 }))
}
