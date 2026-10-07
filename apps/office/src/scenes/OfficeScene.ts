import Phaser from 'phaser'
import type { Employee } from '../api.ts'

/** A named point from the Tiled map's "spots" object layer (desk-1..n, door, huddle). */
type Spot = { name: string; type: string; x: number; y: number }

const LABEL: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: 'monospace',
  fontSize: '8px',
  color: '#ffffff',
  stroke: '#1d2029',
  strokeThickness: 2,
}

const TINTS = [0xff8a65, 0xffd54f, 0x81c784, 0x64b5f6, 0xba68c8, 0x4dd0e1, 0xf06292, 0xaed581]

export type OfficeData = { employees: Employee[] }

export class OfficeScene extends Phaser.Scene {
  // Not `data`: Phaser.Scene already has a `data` (its DataManager).
  private readonly office: OfficeData

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
    const desks = all.filter((s) => s.type === 'desk')
    const seated = this.office.employees.slice(0, desks.length) // hire order = desk order
    seated.forEach((employee, i) => this.seat(employee.name, desks[i]))

    const standing = this.office.employees.length - seated.length
    const huddle = all.find((s) => s.name === 'huddle')
    if (standing > 0 && huddle) {
      this.add.text(huddle.x, huddle.y, `+${standing} without a desk`, LABEL).setOrigin(0.5).setResolution(4)
    }
    if (this.office.employees.length === 0 && huddle) {
      this.add.text(huddle.x, huddle.y, 'No one hired yet', LABEL).setOrigin(0.5).setResolution(4)
    }
  }

  private seat(name: string, desk: Spot): void {
    this.add.sprite(desk.x, desk.y, 'character', 0).setTint(tintFor(name))
    this.add
      .text(desk.x, desk.y + 9, name, LABEL)
      .setOrigin(0.5, 0)
      .setResolution(4) // render text at 4x so it stays sharp under the 2x zoom
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
