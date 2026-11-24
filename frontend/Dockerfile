# ---- build stage: compile the React app ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# ---- runtime stage: static files on nginx, no Node toolchain ----
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/40-lyftr-config.sh /docker-entrypoint.d/40-lyftr-config.sh
RUN chmod +x /docker-entrypoint.d/40-lyftr-config.sh
COPY --from=build /app/dist /usr/share/nginx/html
# The backend URL is runtime configuration (API_BASE_URL), written to /config.js at start.
ENV API_BASE_URL=http://localhost:8000
EXPOSE 3000
