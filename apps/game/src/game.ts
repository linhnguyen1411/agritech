import Phaser from 'phaser';

import { FarmScene } from './scenes/FarmScene';
import { PreloadScene } from './scenes/PreloadScene';

export function createGame(parent: HTMLElement): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    width: 1280,
    height: 720,
    parent,
    backgroundColor: '#2d5a27',
    scene: [PreloadScene, FarmScene],
    physics: {
      default: 'arcade',
      arcade: { debug: (import.meta as { env?: { DEV?: boolean } }).env?.DEV ?? false },
    },
  });
}
