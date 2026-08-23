FROM node:26-slim AS deps
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@10.15.0 --activate
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile

FROM deps AS builder
ARG NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_DARKNETRA_API_BASE_URL=$NEXT_PUBLIC_DARKNETRA_API_BASE_URL
COPY apps/web apps/web
RUN pnpm --filter @darknetra/web build

FROM node:26-slim AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appuser /app/apps/web/.next/standalone ./
COPY --from=builder --chown=appuser:appuser /app/apps/web/.next/static ./apps/web/.next/static
USER appuser
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
