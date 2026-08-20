# syntax=docker/dockerfile:1.7

FROM node:22.23.1-alpine3.23 AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1


FROM base AS dependencies
COPY package.json package-lock.json ./
RUN npm ci


FROM base AS builder
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_BASE_URL=
ARG NEXT_PUBLIC_MAPBOX_TOKEN=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_MAPBOX_TOKEN=$NEXT_PUBLIC_MAPBOX_TOKEN
RUN npm run build


FROM base AS production-dependencies
ENV NODE_ENV=production
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force


FROM base AS runtime
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup -S -g 10001 riskroute \
    && adduser -S -D -H -u 10001 -G riskroute riskroute

COPY --from=production-dependencies --chown=riskroute:riskroute /app/node_modules ./node_modules
COPY --from=builder --chown=riskroute:riskroute /app/.next ./.next
COPY --from=builder --chown=riskroute:riskroute /app/package.json ./package.json
COPY --from=builder --chown=riskroute:riskroute /app/next.config.js ./next.config.js

USER riskroute
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "const http=require('http');const request=http.get('http://127.0.0.1:3000/',response=>{response.resume();process.exit(response.statusCode>=200&&response.statusCode<400?0:1)});request.setTimeout(3000,()=>request.destroy(new Error('timeout')));request.on('error',()=>process.exit(1))"]

CMD ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
