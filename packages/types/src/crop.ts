import type { Timestamp } from './common';

export interface Crop extends Timestamp {
  id: string;
  name: string;
  growthTimeSeconds: number;
  sellPrice: number;
  buyPrice: number;
  experience: number;
  season: Season[];
}

export type Season = 'spring' | 'summer' | 'fall' | 'winter';
