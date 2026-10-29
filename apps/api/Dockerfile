FROM oven/bun:1.3.10-alpine AS bun

FROM node:22-alpine AS base
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun

FROM base AS build
WORKDIR /workspace
COPY package.json bun.lock ./
COPY apps/api/package.json apps/api/package.json
COPY apps/web/package.json apps/web/package.json
RUN bun install --frozen-lockfile
COPY tsconfig.base.json ./
COPY apps/api apps/api
RUN bun run --filter @tasks/api build

FROM base AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY package.json bun.lock ./
COPY apps/api/package.json apps/api/package.json
COPY apps/web/package.json apps/web/package.json
RUN bun install --frozen-lockfile --production --filter @tasks/api && bun pm cache rm
COPY --from=build /workspace/apps/api/dist apps/api/dist
USER 1000:1000
EXPOSE 3000
CMD ["node", "apps/api/dist/server.js"]
