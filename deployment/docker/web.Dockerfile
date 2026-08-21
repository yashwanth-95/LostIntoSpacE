# LostIntoSpacE web client — built once, served as static files by nginx.

FROM node:20-slim AS build
WORKDIR /build

COPY apps/web/package.json apps/web/package-lock.json apps/web/
COPY packages/simulation-engine/package.json packages/simulation-engine/package-lock.json packages/simulation-engine/
# The engine's dev dependencies too: apps/web compiles its sources directly
# rather than a built artefact, so @types/react and @types/three have to be
# present for the typecheck to see anything but `any`.
RUN cd packages/simulation-engine && npm ci
RUN cd apps/web && npm ci

COPY packages/ packages/
COPY apps/web/ apps/web/
RUN cd apps/web && npm run build

FROM nginx:1.27-alpine AS runtime
COPY deployment/nginx/web.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/apps/web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
