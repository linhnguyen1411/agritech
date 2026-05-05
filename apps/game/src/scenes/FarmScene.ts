import Phaser from 'phaser';

export class FarmScene extends Phaser.Scene {
  constructor() {
    super({ key: 'FarmScene' });
  }

  create() {
    this.add
      .text(this.scale.width / 2, this.scale.height / 2, 'AgriTech Farm Game', {
        fontSize: '48px',
        color: '#ffffff',
      })
      .setOrigin(0.5);
  }

  update() {
    // game loop
  }
}
