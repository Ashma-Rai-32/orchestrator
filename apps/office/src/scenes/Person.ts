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

/**
 * A character in the office: sprite + name label + speech bubble in one Phaser Container,
 * so all three always move together. (Bug fixed: a tween *chain*'s onUpdate does not fire
 * per step in Phaser 4, so separately positioned labels stayed behind at the desk.)
 */
export class Person {
  private readonly body: Phaser.GameObjects.Container
  private readonly sprite: Phaser.GameObjects.Sprite
  private readonly bubble: Phaser.GameObjects.Text
  private readonly home: { x: number; y: number }
  private readonly scene: Phaser.Scene

  constructor(scene: Phaser.Scene, name: string, x: number, y: number, tint: number) {
    this.scene = scene
    this.home = { x, y }
    this.sprite = scene.add.sprite(0, 0, 'character', 0).setTint(tint)
    const label = scene.add.text(0, 9, name, LABEL).setOrigin(0.5, 0).setResolution(4)
    this.bubble = scene.add.text(0, -10, '', BUBBLE).setOrigin(0.5, 1).setResolution(4).setVisible(false)
    this.body = scene.add.container(x, y, [this.sprite, label, this.bubble]).setDepth(y)
  }

  /** Say something above the head; empty text hides the bubble. */
  say(text: string): void {
    this.bubble.setText(shorten(text, 80)).setVisible(text.length > 0)
    // A speaking character comes to the front so the bubble is never hidden.
    this.body.setDepth(text ? 10_000 + this.body.y : this.body.y)
  }

  /** Walk through `points`, then call `done`. Straight lines, no pathfinding yet. */
  walk(points: { x: number; y: number }[], done?: () => void): void {
    this.scene.tweens.killTweensOf(this.body)
    const legs = []
    let from = { x: this.body.x, y: this.body.y }
    for (const to of points) {
      const duration = (Phaser.Math.Distance.BetweenPoints(from, to) / WALK_PIXELS_PER_SECOND) * 1000
      legs.push({ x: to.x, y: to.y, duration, ease: 'Linear' })
      from = to
    }
    this.sprite.play('walk')
    this.scene.tweens.chain({
      targets: this.body,
      tweens: legs,
      onComplete: () => {
        this.sprite.stop().setFrame(0)
        if (!this.bubble.visible) this.body.setDepth(this.body.y) // lower on screen = in front
        done?.()
      },
    })
  }

  goHome(done?: () => void): void {
    this.walk([this.home], done)
  }
}

function shorten(text: string, max: number): string {
  const clean = text.replace(/\s*\[assign_[^\]]*\]/g, '').replace(/\s+/g, ' ').trim()
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}
