FROM node:20-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /repo

COPY pnpm-workspace.yaml package.json pnpm-lock.yaml* ./
COPY packages/types/package.json ./packages/types/
COPY packages/api-client/package.json ./packages/api-client/
COPY apps/game/package.json ./apps/game/

RUN pnpm install --frozen-lockfile

COPY packages/types ./packages/types
COPY packages/api-client ./packages/api-client
COPY apps/game ./apps/game

RUN pnpm --filter @agritech/game build

FROM nginx:alpine
COPY --from=builder /repo/apps/game/dist /usr/share/nginx/html
COPY apps/game/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
