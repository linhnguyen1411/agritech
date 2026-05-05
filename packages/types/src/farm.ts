import type { Timestamp } from './common';

export interface Farm extends Timestamp {
  id: string;
  playerId: string;
  name: string;
  width: number;
  height: number;
  plots: FarmPlot[];
}

export interface FarmPlot {
  x: number;
  y: number;
  cropId?: string;
  plantedAt?: string;
  harvestAt?: string;
  state: PlotState;
}

export type PlotState = 'empty' | 'planted' | 'growing' | 'ready' | 'harvested';
