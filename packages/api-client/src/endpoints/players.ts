import type { CreatePlayerDto, Paginated, Player, UpdatePlayerDto } from '@agritech/types';

import { apiClient } from '../client';

const BASE = '/api/v1/players';

export const playersApi = {
  list: (page = 1, pageSize = 20) =>
    apiClient.get<Paginated<Player>>(BASE, { params: { page, pageSize } }),

  get: (id: string) => apiClient.get<Player>(`${BASE}/${id}`),

  create: (dto: CreatePlayerDto) => apiClient.post<Player>(BASE, dto),

  update: (id: string, dto: UpdatePlayerDto) => apiClient.patch<Player>(`${BASE}/${id}`, dto),

  delete: (id: string) => apiClient.delete(`${BASE}/${id}`),
};
