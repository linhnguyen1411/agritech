import type { Farm } from '@agritech/types';

import { apiClient } from '../client';

const BASE = '/api/v1/farms';

export const farmsApi = {
  list: (playerId: string) => apiClient.get<Farm[]>(BASE, { params: { playerId } }),

  get: (id: string) => apiClient.get<Farm>(`${BASE}/${id}`),

  plant: (farmId: string, x: number, y: number, cropId: string) =>
    apiClient.post(`${BASE}/${farmId}/plant`, { x, y, cropId }),

  harvest: (farmId: string, x: number, y: number) =>
    apiClient.post(`${BASE}/${farmId}/harvest`, { x, y }),
};
