FROM python:3.12-slim-bookworm AS ml_runtime
COPY research/ml-requirements.txt /tmp/ml-requirements.txt
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r /tmp/ml-requirements.txt

FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM research_runtime AS runtime
USER root
WORKDIR /app
ARG CODEX_VERSION=0.153.4
RUN npm install --global @openai/codex@${CODEX_VERSION} && npm cache clean --force
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libexpat1 libuuid1 && rm -rf /var/lib/apt/lists/*
COPY --from=ml_runtime /usr/local /usr/local
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/skills ./skills
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/package.json /app/next.config.ts /app/assistant-instructions.md ./
COPY --chown=node:node docker-entrypoint.sh ./docker-entrypoint.sh
RUN mkdir -p /app/.codex-chat && chown node:node /app/.codex-chat
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 CODEX_HOME=/app/.codex-chat/codex-home DARKNETRA_ML_PYTHON=/usr/local/bin/python3.12 PYTHONDONTWRITEBYTECODE=1
USER node
EXPOSE 3000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
