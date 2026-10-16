# Сборка обоих PWA и раздача через nginx (сервис web в корневом docker-compose.yml).
FROM node:22-alpine AS build
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 CI=1
RUN corepack enable

# Сначала манифесты — слой зависимостей кэшируется, пока не меняется lockfile.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/client/package.json apps/client/
COPY apps/master/package.json apps/master/
COPY packages/api/package.json packages/api/
COPY packages/mocks/package.json packages/mocks/
COPY packages/ui/package.json packages/ui/
COPY packages/pwa/package.json packages/pwa/
COPY packages/telegram-login/package.json packages/telegram-login/
COPY e2e/package.json e2e/
RUN pnpm install --frozen-lockfile

COPY . .
# Публичный VAPID-ключ для Web Push (пусто — подписка недоступна).
ARG VITE_VAPID_PUBLIC_KEY=
ENV VITE_VAPID_PUBLIC_KEY=${VITE_VAPID_PUBLIC_KEY}
RUN pnpm --filter @beauty/client build && pnpm --filter @beauty/master build

FROM nginx:1.29-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/app.conf nginx/security-headers.conf /etc/nginx/snippets/
COPY --from=build /app/apps/client/dist /usr/share/nginx/client
COPY --from=build /app/apps/master/dist /usr/share/nginx/master
