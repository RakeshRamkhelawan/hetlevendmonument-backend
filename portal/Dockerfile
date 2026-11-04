# ============================================================================
# OPTIMIZED MULTI-STAGE BUILD - Levend Monument Heritage Portal
# ============================================================================
# Build commands:
#   PRODUCTION:  docker build -t levend-monument-portal:prod ./portal
#   WITH CACHE:  DOCKER_BUILDKIT=1 docker build -t levend-monument-portal:prod ./portal
#   CLEAN BUILD: docker build --no-cache -t levend-monument-portal:prod ./portal
# ============================================================================

# ==================== DEPENDENCIES STAGE ====================
FROM node:20-alpine AS deps

WORKDIR /app

# Copy package files for deterministic layer caching
COPY package.json package-lock.json* ./

# Install dependencies using npm cache mount
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps

# ==================== DEVELOPMENT STAGE ====================
FROM deps AS development

WORKDIR /app

COPY . .

ENV NODE_ENV=development
EXPOSE 5174

CMD ["npm", "run", "dev", "--", "--host", "--port", "5174"]

# ==================== BUILD STAGE ====================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build arguments for environment configuration
ARG VITE_ENVIRONMENT=production
ARG VITE_API_URL=/api/v1
# Publieke hCaptcha-sitekey (geen geheim); leeg = widget toont niets.
ARG VITE_HCAPTCHA_SITE_KEY=

ENV VITE_ENVIRONMENT=${VITE_ENVIRONMENT}
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_HCAPTCHA_SITE_KEY=${VITE_HCAPTCHA_SITE_KEY}
ENV NODE_ENV=production

# Run build (TypeScript type-check + Vite bundler)
RUN NODE_OPTIONS="--max-old-space-size=4096" npm run build && \
    echo "[OK] Portal build completed"

# Verify build output exists
RUN test -d dist && test -f dist/index.html && \
    echo "[OK] Build artifacts verified"

# ==================== PRODUCTION STAGE ====================
FROM nginx:alpine AS production

LABEL org.opencontainers.image.title="Levend Monument Heritage Portal"
LABEL org.opencontainers.image.description="Public Heritage Portal - Levend Monument"
LABEL org.opencontainers.image.version="1.0.0"

# Remove default nginx config; ours is a template that gets API_UPSTREAM at start-up
# (docker-entrypoint.d/20-envsubst-on-templates.sh of the official image).
RUN rm /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/snippets /etc/nginx/templates
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
# Default for docker compose; Azure Container Apps sets it to the internal API app.
ENV API_UPSTREAM=http://backend:8000
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

# Copy built assets to nginx document root
COPY --from=builder /app/dist /usr/share/nginx/html

# Configure proper permissions for non-root nginx execution
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid && \
    chown -R nginx:nginx /etc/nginx/conf.d

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5174/health || exit 1

EXPOSE 5174

# Run nginx as non-root user
USER nginx

CMD ["nginx", "-g", "daemon off;"]
