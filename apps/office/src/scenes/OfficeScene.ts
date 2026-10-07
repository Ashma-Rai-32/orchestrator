import Phaser from 'phaser'

/** A named point from the Tiled map's "spots" object layer (desk-1..n, door, huddle). */
type Spot = { name: string; type: string; x: number; y: number }

const LABEL: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: 'monospace',
  fontSize: '8px',
  color: '#ffffff',
  stroke: '#1d2029',
  strokeThickness: 2,
}

const DEMO_TEAM = [
  { name: 'Pixel 1', tint: 0xff8a65 },
  { name: 'Pixel 2', tint: 0xffd54f },
  { name: 'Ada', tint: 0x81c784 },
  { name: 'Tess', tint: 0x64b5f6 },
]

export class OfficeScene extends Phaser.Scene {
  constructor() {
    super('office')
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

    const desks = spots(map).filter((s) => s.type === 'desk')
    DEMO_TEAM.forEach((member, i) => this.seat(member.name, member.tint, desks[i]))
  }

  private seat(name: string, tint: number, desk: Spot): void {
    this.add.sprite(desk.x, desk.y, 'character', 0).setTint(tint)
    this.add
      .text(desk.x, desk.y + 9, name, LABEL)
      .setOrigin(0.5, 0)
      .setResolution(4) // render text at 4x so it stays sharp under the 2x zoom
  }
}

function spots(map: Phaser.Tilemaps.Tilemap): Spot[] {
  const layer = map.getObjectLayer('spots')
  if (!layer) throw new Error('object layer "spots" missing from office.tmj')
  return layer.objects.map((o) => ({ name: o.name, type: o.type, x: o.x ?? 0, y: o.y ?? 0 }))
}
