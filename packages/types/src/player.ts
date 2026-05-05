import type { Timestamp } from './common';

export interface Player extends Timestamp {
  id: string;
  username: string;
  walletAddress?: string;
  level: number;
  experience: number;
  gold: number;
}

export interface CreatePlayerDto {
  username: string;
  walletAddress?: string;
}

export interface UpdatePlayerDto {
  username?: string;
  walletAddress?: string;
}
