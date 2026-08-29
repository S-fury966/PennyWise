# ============================================================================
# Frontend Dockerfile — AI Finance Controller (Reconciliation Agent)
# ============================================================================
# Multi-stage build:
#   Stage 1 (build): Node.js 22 — installs deps, builds the Vite + React app
#   Stage 2 (serve): nginx — serves the static build output
#
# Node 22 LTS chosen to match the modern dependency versions:
# Vite 8, TypeScript 6, React 19, @vitejs/plugin-react 6 all require
# Node 18+. Node 22 is the current LTS release.
#
# The nginx config reverse-proxies /api requests to the "backend" service
# (resolved via Docker Compose's internal DNS), so the browser never makes
# a cross-origin request — no CORS configuration needed on the backend
# for the containerized setup.
# ============================================================================

# ---- Stage 1: Build ----
FROM node:22-slim AS build

WORKDIR /app

# Copy dependency manifests first for layer caching.
COPY package.json package-lock.json ./

# Use npm ci (not npm install) for reproducible, lockfile-only installs.
# --ignore-scripts skips lifecycle scripts for security; most deps
# don't need them, and we don't want postinstall hooks running in a
# build container.
RUN npm ci --ignore-scripts

# Copy the rest of the frontend source.
COPY . .

# Build the production bundle.
# Vite writes output to dist/ by default.
RUN npm run build

# ---- Stage 2: Serve ----
FROM nginx:stable-alpine

# Remove the default nginx config and replace with ours.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy only the built output from Stage 1.
# This guarantees node_modules, source files, and build tooling
# are NOT present in the final image.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
