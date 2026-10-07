import Phaser from 'phaser'

const WALK_PIXELS_PER_SECOND = 70

export const LABEL: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: 'monospace',
  fontSize: '8px',
  color: '#ffffff',
  stroke: '#1d2029',
  strokeThickness: 2,
}

const BUBBLE: Phaser.Types.GameObjects.Text.TextStyle = {
  fontFamily: 'system-ui, sans-serif',
  fontSize: '7px',
  color: '#1d2029',
  backgroundColor: '#ffffffee',
  padding: { x: 3, y: 2 },
  wordWrap: { width: 90 },
}

/** A character in the office: sprite + name label + speech bubble, moved by tweens. */
export class Person {
  private readonly sprite: Phaser.GameObjects.Sprite
  private readonly label: Phaser.GameObjects.Text
  private readonly bubble: Phaser.GameObjects.Text
  private readonly home: { x: number; y: number }
  private readonly scene: Phaser.Scene

  constructor(scene: Phaser.Scene, name: string, x: number, y: number, tint: number) {
    this.scene = scene
    this.home = { x, y }
    this.sprite = scene.add.sprite(x, y, 'character', 0).setTint(tint).setDepth(y)
    this.label = scene.add.text(x, y + 9, name, LABEL).setOrigin(0.5, 0).setResolution(4).setDepth(1000)
    this.bubble = scene.add
      .text(x, y - 10, '', BUBBLE)
      .setOrigin(0.5, 1)
      .setResolution(4)
      .setDepth(2000)
      .setVisible(false)
  }

  /** Say something above the head; empty text hides the bubble. */
  say(text: string): void {
    this.bubble.setText(shorten(text, 80)).setVisible(text.length > 0)
  }

  /** Walk to (x, y), then to each next point, then call `done`. Straight lines, no pathfinding yet. */
  walk(points: { x: number; y: number }[], done?: () => void): void {
    this.scene.tweens.killTweensOf([this.sprite, this.label, this.bubble])
    const legs = []
    let from = { x: this.sprite.x, y: this.sprite.y }
    for (const to of points) {
      const duration = (Phaser.Math.Distance.BetweenPoints(from, to) / WALK_PIXELS_PER_SECOND) * 1000
      legs.push({ x: to.x, y: to.y, duration, ease: 'Linear' })
      from = to
    }
    this.sprite.play('walk')
    this.scene.tweens.chain({
      targets: this.sprite,
      tweens: legs,
      onUpdate: () => this.follow(),
      onComplete: () => {
        this.sprite.stop().setFrame(0)
        this.follow()
        done?.()
      },
    })
  }

  goHome(done?: () => void): void {
    this.walk([this.home], done)
  }

  /** Label and bubble track the sprite; depth sorts characters by y (who is in front). */
  private follow(): void {
    const { x, y } = this.sprite
    this.sprite.setDepth(y)
    this.label.setPosition(x, y + 9)
    this.bubble.setPosition(x, y - 10)
  }
}

function shorten(text: string, max: number): string {
  const clean = text.replace(/\s*\[assign_[^\]]*\]/g, '').replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}
